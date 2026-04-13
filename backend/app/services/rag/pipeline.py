"""
RAG Pipeline — orchestrates retrieval and generation.
"""
import time
from typing import List, Dict, Any, AsyncGenerator, Optional

from app.core.config import settings
from app.services.rag.retrieval import multi_source_retrieve, hybrid_retrieve
from app.services.rag.generation import generate_answer, stream_answer
from app.services.rag.date_filter import extract_date_filter
import re

SYSTEM_PROMPT = """You are IntelliRAG, an intelligent enterprise knowledge assistant for ACL Digital.
Answer questions based on the provided context documents and conversation history.

Core Rules:
- Be precise and factual. Only use information from context documents or conversation history.
- TRUST the context — if documents are provided, they are relevant.
- Use conversation history to answer follow-up questions.
- Never say you cannot find information if the answer exists in conversation history.
- Format answers clearly with bullet points for lists.

When asked for a CHART or VISUALIZATION:
- If the data is available in context OR conversation history, respond with:
  BAR_CHART: (for bar charts)
  PIE_CHART: (for pie charts)
  LINE_CHART: (for line charts)
  Followed by bullet points: "- Label: numeric_value"
  Then a brief summary.
- Use ONLY real numeric values. Never write "Not available" as a value.
- If chart data is not available anywhere, say so clearly in plain text without chart format.

When NOT asked for a chart:
- Respond in plain conversational text with bullet points.
- Do NOT use BAR_CHART/PIE_CHART/LINE_CHART prefixes."""


def _strip_chart_keywords(question: str) -> str:
    """Remove visualization keywords so semantic search finds content, not chart types."""
    cleaned = re.sub(
        r'\b(as|in|show|display|convert|make|create|give me|render)\s+(a\s+)?'
        r'(bar|pie|line|donut|chart|graph|visualization|table|visual)\b',
        '', question, flags=re.IGNORECASE
    ).strip()
    return cleaned if cleaned else question


def _build_context(chunks: List[Dict]) -> str:
    """Format retrieved chunks into a context block for the LLM."""
    truncated = [{**c, "text": c["text"][:500]} for c in chunks]
    parts = []
    for i, chunk in enumerate(truncated, 1):
        file_date = chunk.get("file_date", "")
        date_str = f" | Date: {file_date[:10]}" if file_date else ""
        parts.append(f"[Source {i}: {chunk['filename']}{date_str}]\n{chunk['text']}")
    return "\n\n".join(parts)


def _build_messages(question: str, context: str, history: List[Dict]) -> List[Dict]:
    """Assemble the message list for the LLM (system + history + user)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": (
            f"Context documents:\n{context}\n\n---\n"
            f"Question: {question}\n\nAnswer based strictly on the context above."
        ),
    })
    return messages


def _extract_sources(chunks: List[Dict]) -> List[Dict]:
    """Deduplicate and format source references."""
    seen: set = set()
    sources = []
    for chunk in chunks:
        key = f"{chunk['document_id']}_{chunk['chunk_index']}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "filename": chunk["filename"],
                "document_id": chunk["document_id"],
                "chunk_index": chunk["chunk_index"],
                "relevance_score": round(chunk["score"], 3),
                "web_url": chunk.get("web_url", ""),
                "file_path": chunk.get("file_path", ""),
                "source_type": chunk.get("source_type", ""),
            })
    return sources


async def retrieve_and_generate(
    question: str,
    tenant_slug: str,
    top_k: int = None,
    user_context: Dict = None,
    history: List[Dict] = None,
    sources: List[str] = None,
) -> Dict[str, Any]:
    """Full RAG pipeline: retrieve relevant chunks → build context → generate answer."""
    start = time.time()
    top_k = top_k or settings.TOP_K
    history = history or []

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_start = time.time()
    date_filter = extract_date_filter(question)
    search_question = _strip_chart_keywords(question)
    if date_filter:
        search_question = f"{date_filter} {search_question}"

    chunks = await multi_source_retrieve(search_question, tenant_slug, top_k, sources, date_filter=date_filter)
    retrieval_ms = int((time.time() - retrieval_start) * 1000)

    if not chunks:
        return {
            "answer": "I could not find relevant information in the available documents. Please ensure documents have been uploaded for this knowledge base.",
            "sources": [],
            "confidence": 0.0,
            "retrieval_ms": retrieval_ms,
            "generation_ms": 0,
            "total_ms": int((time.time() - start) * 1000),
            "chunks_used": 0,
        }

    # ── Generation ────────────────────────────────────────────────────────────
    context = _build_context(chunks[:3])
    messages = _build_messages(question, context, history[-4:])

    gen_start = time.time()
    answer = await generate_answer(messages)
    generation_ms = int((time.time() - gen_start) * 1000)

    extracted_sources = _extract_sources(chunks)
    confidence = round(sum(c["score"] for c in chunks) / len(chunks), 2)

    return {
        "answer": answer,
        "sources": extracted_sources,
        "confidence": min(confidence * 1.2, 1.0),
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "total_ms": int((time.time() - start) * 1000),
        "chunks_used": len(chunks),
    }


async def stream_retrieve_and_generate(
    question: str,
    tenant_slug: str,
    top_k: int = None,
    history: List[Dict] = None,
) -> AsyncGenerator[str, None]:
    """Streaming RAG pipeline for real-time token delivery."""
    top_k = top_k or settings.TOP_K
    history = history or []
    chunks = await hybrid_retrieve(question, tenant_slug, top_k)

    if not chunks:
        yield "I could not find relevant information in the available documents."
        return

    context = _build_context(chunks[:3])
    messages = _build_messages(question, context, history[-4:])

    async for token in stream_answer(messages):
        yield token
