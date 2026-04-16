"""
RAG Pipeline — orchestrates retrieval and generation.
"""
import time
import re
from typing import List, Dict, Any, AsyncGenerator, Optional

from app.core.config import settings
from app.services.rag.retrieval import multi_source_retrieve, hybrid_retrieve
from app.services.rag.generation import generate_answer, stream_answer
from app.services.rag.date_filter import extract_date_filter

SYSTEM_PROMPT = """You are IntelliRAG, an intelligent enterprise AI assistant for ACL Digital.

RULES:
1. Answer ONLY from the provided context documents. Do not calculate or estimate.
2. If a document contains the exact answer (e.g. "Bear Case: $26M"), quote it directly.
3. For greetings, respond warmly without searching documents.
4. For charts, use BAR_CHART: or PIE_CHART: prefix with "- Label: value" bullets.
5. NEVER say "not explicitly mentioned" if the context contains the answer.
6. NEVER calculate your own estimates when actual figures exist in the context.
7. If context has "Bear Case $26M 15% Growth" — the answer IS $26M at 15% growth. State it directly."""

GREETING_PATTERN = re.compile(
    r'^\(hi|hello|hey|good morning|good afternoon|good evening|how are you|what can you do|who are you\)\b',
    re.IGNORECASE
)

def _is_greeting(question: str) -> bool:
    return bool(GREETING_PATTERN.match(question.strip()))

def _strip_chart_keywords(question: str) -> str:
    cleaned = re.sub(
        r'\b(as|in|show|display|give me|render|make|create)\s+(a\s+)?(bar|pie|line|donut)?\s*(chart|graph|visualization|visual)\b',
        '', question, flags=re.IGNORECASE
    ).strip()
    return cleaned if cleaned else question

def _build_context(chunks: List[Dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        text = chunk["text"][:600]
        date_str = f" | Date: {chunk['file_date'][:10]}" if chunk.get("file_date") else ""
        parts.append(f"[Source {i}: {chunk['filename']}{date_str}]\n{text}")
    return "\n\n".join(parts)

def _build_messages(question: str, context: str, history: List[Dict]) -> List[Dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    user_content = f"Context documents:\n{context}\n\n---\nQuestion: {question}" if context else f"Question: {question}"
    messages.append({"role": "user", "content": user_content})
    return messages

def _extract_sources(chunks: List[Dict]) -> List[Dict]:
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
    start = time.time()
    top_k = top_k or 8
    history = history or []

    if _is_greeting(question):
        messages = _build_messages(question, "", history)
        gen_start = time.time()
        answer = await generate_answer(messages)
        return {"answer": answer, "sources": [], "confidence": 1.0,
                "retrieval_ms": 0, "generation_ms": int((time.time()-gen_start)*1000),
                "total_ms": int((time.time()-start)*1000), "chunks_used": 0}

    retrieval_start = time.time()
    date_filter = extract_date_filter(question)
    search_question = _strip_chart_keywords(question)
    if date_filter:
        search_question = f"{date_filter} {search_question}"

    chunks = await multi_source_retrieve(search_question, tenant_slug, top_k, sources, date_filter=date_filter)
    retrieval_ms = int((time.time() - retrieval_start) * 1000)

    if not chunks:
        return {"answer": "I could not find relevant information in the available documents.",
                "sources": [], "confidence": 0.0, "retrieval_ms": retrieval_ms,
                "generation_ms": 0, "total_ms": int((time.time()-start)*1000), "chunks_used": 0}

    context = _build_context(chunks)
    messages = _build_messages(question, context, history)
    gen_start = time.time()
    answer = await generate_answer(messages)
    generation_ms = int((time.time() - gen_start) * 1000)
    extracted_sources = _extract_sources(chunks)
    confidence = round(sum(c["score"] for c in chunks) / len(chunks), 2)

    return {"answer": answer, "sources": extracted_sources,
            "confidence": min(confidence * 1.2, 1.0), "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms, "total_ms": int((time.time()-start)*1000),
            "chunks_used": len(chunks)}

async def stream_retrieve_and_generate(
    question: str, tenant_slug: str, top_k: int = None, history: List[Dict] = None,
) -> AsyncGenerator[str, None]:
    top_k = top_k or 8
    history = history or []
    if _is_greeting(question):
        async for token in stream_answer(_build_messages(question, "", history)):
            yield token
        return
    chunks = await hybrid_retrieve(question, tenant_slug, top_k)
    context = _build_context(chunks) if chunks else ""
    async for token in stream_answer(_build_messages(question, context, history)):
        yield token
