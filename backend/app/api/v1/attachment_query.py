"""
Attachment Query API — handles queries with file/image attachments.

Enterprise features:
- Images: routed to Groq vision model (llama-3.2-11b-vision-preview)
- Documents: text extracted in-memory, prepended as context to 70b model
- Supported: PDF, DOCX, XLSX, PPTX, PNG, JPG, JPEG, WEBP
- No permanent storage — files processed in-memory only
- Falls back to text query if attachment processing fails
"""
import base64
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.services.memory import get_or_create_session, save_message, get_history
from app.services.rag.generation import generate_answer
from app.services.analytics import log_query
from app.services.rag.pipeline import retrieve_and_generate

log = logging.getLogger("intellirag.attachment")
router = APIRouter()

# Supported formats
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOCUMENT_TYPES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".md"}

# Vision model
VISION_MODEL = "llama-3.2-11b-vision-preview"
MAX_FILE_SIZE_MB = 10


# ── Text extraction from documents ───────────────────────────────────────────

async def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from uploaded document for use as query context."""
    ext = Path(filename).suffix.lower()

    try:
        if ext == ".pdf":
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n\n".join(pages)[:8000]  # Cap at 8K chars

        elif ext in (".docx", ".doc"):
            import io
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paras)[:8000]

        elif ext in (".xlsx", ".xls"):
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sections = []
            for sheet_name in wb.sheetnames[:5]:  # Max 5 sheets
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    values = [str(v).strip() if v is not None else "" for v in row]
                    if any(v for v in values):
                        rows.append(" | ".join(values))
                if rows:
                    sections.append(f"Sheet: {sheet_name}\n" + "\n".join(rows[:50]))
            return "\n\n".join(sections)[:8000]

        elif ext in (".pptx", ".ppt"):
            import io
            from pptx import Presentation
            prs = Presentation(io.BytesIO(file_bytes))
            slides = []
            for i, slide in enumerate(prs.slides[:20], 1):  # Max 20 slides
                texts = [shape.text.strip() for shape in slide.shapes
                         if hasattr(shape, "text") and shape.text.strip()]
                if texts:
                    slides.append(f"Slide {i}:\n" + "\n".join(texts))
            return "\n\n".join(slides)[:8000]

        elif ext in (".txt", ".csv", ".md"):
            return file_bytes.decode("utf-8", errors="ignore")[:8000]

    except Exception as e:
        log.warning(f"[Attachment] Text extraction failed for {filename}: {e}")

    return ""


# ── Main attachment endpoint ──────────────────────────────────────────────────

@router.post("/api/query/with-attachment")
async def query_with_attachment(
    question: str = Form(...),
    tenant: str = Form("general"),
    session_id: Optional[str] = Form(None),
    sources: Optional[str] = Form(None),  # comma-separated
    file: UploadFile = File(...),
):
    """
    Handle a query with an attached file or image.

    Images → Groq Vision model (sees the image directly)
    Documents → Extract text → Use as context with standard 70b model
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # File size check
    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Maximum is {MAX_FILE_SIZE_MB}MB."
        )

    filename = file.filename or "attachment"
    ext = Path(filename).suffix.lower()
    source_list = [s.strip() for s in sources.split(",")] if sources else None

    # Session & history
    user_session_id = await get_or_create_session(session_id, tenant, None)
    history = await get_history(user_session_id, limit=4)

    import time
    start = time.time()

    # ── Route: Image → Vision model ───────────────────────────────────────────
    if ext in IMAGE_TYPES:
        log.info(f"[Attachment] Image query: {filename} ({size_mb:.1f}MB)")

        # Detect media type
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        media_type = media_type_map.get(ext, "image/jpeg")
        image_b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

        # Build vision message
        messages = [
            {
                "role": "system",
                "content": (
                    "You are IntelliRAG, an enterprise AI assistant for ACL Digital. "
                    "Analyze the attached image carefully and answer the user's question "
                    "based on what you see. Be specific, accurate, and professional. "
                    "If the image contains text, data, or charts — read and interpret them precisely."
                )
            }
        ]

        # Add conversation history
        for msg in history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Vision message with image
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_b64}"
                    }
                },
                {
                    "type": "text",
                    "text": question
                }
            ]
        })

        # Call vision model via Groq
        try:
            import asyncio
            from groq import Groq
            from app.core.config import settings

            def _call_vision():
                client = Groq(api_key=settings.GROQ_API_KEY)
                response = client.chat.completions.create(
                    model=VISION_MODEL,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                )
                return response.choices[0].message.content

            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(None, _call_vision)

        except Exception as e:
            log.error(f"[Attachment] Vision model failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Image analysis failed. Please try again."
            )

        generation_ms = int((time.time() - start) * 1000)

        # Save to memory
        await save_message(user_session_id, "user", f"[Image: {filename}] {question}")
        await save_message(user_session_id, "assistant", answer)

        query_id = await log_query(
            tenant_slug=tenant,
            question=f"[Image: {filename}] {question}",
            answer=answer,
            sources=[],
            confidence_score=0.95,
            retrieval_ms=0,
            generation_ms=generation_ms,
            total_ms=generation_ms,
            session_id=user_session_id,
        )

        return {
            "query_id": query_id,
            "session_id": user_session_id,
            "answer": answer,
            "sources": [{
                "filename": filename,
                "document_id": "attachment",
                "chunk_index": 0,
                "relevance_score": 1.0,
                "web_url": "",
                "file_path": "",
                "source_type": "attachment_image",
            }],
            "confidence": 0.95,
            "retrieval_ms": 0,
            "generation_ms": generation_ms,
            "total_ms": generation_ms,
            "chunks_used": 1,
            "attachment_type": "image",
            "attachment_name": filename,
        }

    # ── Route: Document → Extract text → Use as context ──────────────────────
    elif ext in DOCUMENT_TYPES:
        log.info(f"[Attachment] Document query: {filename} ({size_mb:.1f}MB)")

        extracted_text = await extract_text_from_file(file_bytes, filename)

        if not extracted_text.strip():
            raise HTTPException(
                status_code=422,
                detail=f"Could not extract text from {filename}. "
                       f"The file may be scanned/image-based or corrupted."
            )

        # Also search knowledge base for additional context
        kb_result = await retrieve_and_generate(
            question=question,
            tenant_slug=tenant,
            top_k=3,
            history=history,
            sources=source_list,
        )

        # Build enhanced context: attachment first, then KB
        attachment_context = (
            f"[Attached Document: {filename}]\n"
            f"{extracted_text}\n\n"
            f"---END OF ATTACHMENT---"
        )

        kb_context = ""
        if kb_result.get("sources"):
            kb_context = (
                f"\n\n[Additional context from knowledge base]:\n"
                + "\n\n".join(
                    f"[{s['filename']}]: {s.get('text', '')[:300]}"
                    for s in kb_result.get("sources", [])[:2]
                )
            )

        full_context = attachment_context + kb_context

        messages = [
            {
                "role": "system",
                "content": (
                    "You are IntelliRAG, an enterprise AI assistant for ACL Digital. "
                    "The user has attached a document. Answer their question using the "
                    "attached document as your PRIMARY source. Be specific and quote "
                    "exact values when they appear. If the document doesn't contain "
                    "the answer, say so clearly."
                )
            }
        ]
        for msg in history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({
            "role": "user",
            "content": f"Context:\n{full_context}\n\n---\n\nQuestion: {question}"
        })

        answer = await generate_answer(messages)
        total_ms = int((time.time() - start) * 1000)

        await save_message(user_session_id, "user", f"[Doc: {filename}] {question}")
        await save_message(user_session_id, "assistant", answer)

        # Build source list: attachment first
        all_sources = [{
            "filename": filename,
            "document_id": "attachment",
            "chunk_index": 0,
            "relevance_score": 1.0,
            "web_url": "",
            "file_path": "",
            "source_type": "attachment_document",
        }]

        query_id = await log_query(
            tenant_slug=tenant,
            question=f"[Doc: {filename}] {question}",
            answer=answer,
            sources=all_sources,
            confidence_score=0.9,
            retrieval_ms=0,
            generation_ms=total_ms,
            total_ms=total_ms,
            session_id=user_session_id,
        )

        return {
            "query_id": query_id,
            "session_id": user_session_id,
            "answer": answer,
            "sources": all_sources,
            "confidence": 0.9,
            "retrieval_ms": 0,
            "generation_ms": total_ms,
            "total_ms": total_ms,
            "chunks_used": 1,
            "attachment_type": "document",
            "attachment_name": filename,
        }

    else:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {ext}. "
                   f"Supported: PDF, DOCX, XLSX, PPTX, PNG, JPG, WEBP"
        )
