"""
RAG Pipeline — orchestrates retrieval + generation.
Handles both semantic queries and structured data queries (ranking/comparison).
"""
import time
import re
import logging
from typing import List, Dict, Any, AsyncGenerator, Optional

from app.core.config import settings
from app.services.rag.retrieval import multi_source_retrieve, hybrid_retrieve
from app.services.rag.generation import generate_answer, stream_answer
from app.services.rag.date_filter import extract_date_filter

log = logging.getLogger("intellirag.pipeline")

SYSTEM_PROMPT = """You are IntelliRAG, an intelligent enterprise knowledge assistant for ACL Digital.

## Core Rules

### Answering from documents
- Answer based ONLY on the provided context documents
- Quote exact values when they exist: if context says "Bear Case: $26M", answer is "$26M"
- Never calculate or estimate when exact figures are present in context
- If multiple documents have relevant info, synthesize across them

### Structured data answers (rankings, comparisons)
- When context shows ranked/sorted data, present the top results clearly
- Show the metric value for each entry
- State which document the data comes from

### When context has partial info
- Use what is available and clearly state what was found
- Do NOT say "not found" if context contains related information

### When context has NO relevant info
- Clearly state the information is not in the available documents

### Charts and visualizations
- Use PIE_CHART: or BAR_CHART: or LINE_CHART: prefix
- Format: "- Label: numeric_value" (one per line)
- Only use real numbers from documents

### Greetings and general conversation
- Respond warmly and naturally
- Do not search documents for greetings

### Formatting
- Use bullet points for lists
- Use bold for key metrics and numbers
- Keep answers concise and factual"""

GREETING_RE = re.compile(
    r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|how are you|"
    r"what can you do|who are you|what is intellirag)\b",
    re.IGNORECASE,
)

CHART_WORDS_RE = re.compile(
    r"\b(as|in|show|display|give\s+me|render|make|create|draw)\s+(a\s+)?"
    r"(bar|pie|line|donut)?\s*(chart|graph|visualization|visual)\b",
    re.IGNORECASE,
)


def _is_greeting(question: str) -> bool:
    return bool(GREETING_RE.match(question.strip()))


def _strip_chart_keywords(question: str) -> str:
    cleaned = CHART_WORDS_RE.sub("", question).strip()
    return cleaned if cleaned else question


def _build_context(chunks: List[Dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        text = chunk["text"][:400]
        date_str = f" | Date: {chunk['file_date'][:10]}" if chunk.get("file_date") else ""
        parts.append(f"[Source {i}: {chunk['filename']}{date_str}]\n{text}")
    return "\n\n---\n\n".join(parts)


def _build_ranked_context(ranked_rows: List[Dict], question: str) -> str:
    """Build context from ranked structured data results."""
    metric = ranked_rows[0]['metric'] if ranked_rows else 'value'
    direction = 'highest' if any(w in question.lower() for w in ['highest', 'most', 'top', 'best', 'largest']) else 'lowest'

    lines = [f"[Structured Data: {ranked_rows[0]['filename']} — Ranked by {metric} ({direction} first)]"]
    lines.append(f"Total records found: {len(ranked_rows)}")
    lines.append("")

    for i, row in enumerate(ranked_rows[:10], 1):
        lines.append(f"{i}. {row['name']}: {row['metric_value']:.1f}{'%' if metric == 'growth' else ''}")

    return "\n".join(lines)


def _build_messages(question: str, context: str, history: List[Dict]) -> List[Dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in (history or [])[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    if context:
        user_content = f"Context documents:\n\n{context}\n\n---\n\nQuestion: {question}"
    else:
        user_content = f"Question: {question}"
    messages.append({"role": "user", "content": user_content})
    return messages


def _extract_sources(chunks: List[Dict]) -> List[Dict]:
    seen: set = set()
    sources = []
    for chunk in chunks:
        key = f"{chunk['filename']}_{chunk['chunk_index']}"
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

    # Greetings: skip retrieval
    if _is_greeting(question):
        messages = _build_messages(question, "", history)
        gen_start = time.time()
        answer = await generate_answer(messages)
        return {
            "answer": answer, "sources": [], "confidence": 1.0,
            "retrieval_ms": 0,
            "generation_ms": int((time.time() - gen_start) * 1000),
            "total_ms": int((time.time() - start) * 1000),
            "chunks_used": 0,
        }

    retrieval_start = time.time()
    date_filter = extract_date_filter(question)
    search_question = _strip_chart_keywords(question)
    if date_filter:
        search_question = f"{date_filter} {search_question}"

    # Detect ranking/comparison queries → use structured query handler
    context = ""
    extracted_sources = []
    chunks = []

    try:
        from app.services.structured_query import is_ranking_query, handle_ranking_query

        if is_ranking_query(question) and not date_filter:
            # Resolve collection name
            source_map = {
                "localfs": "intellirag_localfs",
                "gdrive": "intellirag_gdrive",
                "uploaded": "intellirag_uploaded",
            }
            active_sources = sources or ["uploaded"]
            collection = source_map.get(active_sources[0], f"intellirag_{active_sources[0]}")

            ranked_rows = await handle_ranking_query(question, collection)

            if ranked_rows:
                log.info(f"[Pipeline] Structured query returned {len(ranked_rows)} ranked rows")
                context = _build_ranked_context(ranked_rows, question)
                # Build synthetic source entries from ranked rows
                seen = set()
                for row in ranked_rows[:5]:
                    key = row['filename']
                    if key not in seen:
                        seen.add(key)
                        extracted_sources.append({
                            "filename": row['filename'],
                            "document_id": row['document_id'],
                            "chunk_index": row['chunk_index'],
                            "relevance_score": 0.99,
                            "web_url": "",
                            "file_path": "",
                            "source_type": "localfs",
                        })

    except Exception as e:
        log.warning(f"[Pipeline] Structured query failed, falling back to vector: {e}")

    # Fall back to regular vector retrieval if structured query didn't work
    if not context:
        chunks = await multi_source_retrieve(
            search_question, tenant_slug, top_k, sources,
            date_filter=date_filter,
        )
        extracted_sources = _extract_sources(chunks) if chunks else []
        context = _build_context(chunks) if chunks else ""

    retrieval_ms = int((time.time() - retrieval_start) * 1000)

    if not context:
        return {
            "answer": "I could not find relevant information in the available documents.",
            "sources": [], "confidence": 0.0,
            "retrieval_ms": retrieval_ms, "generation_ms": 0,
            "total_ms": int((time.time() - start) * 1000),
            "chunks_used": 0,
        }

    messages = _build_messages(question, context, history)
    gen_start = time.time()
    answer = await generate_answer(messages)
    generation_ms = int((time.time() - gen_start) * 1000)

    avg_score = (sum(c["score"] for c in chunks) / len(chunks)) if chunks else 0.95
    confidence = round(min(avg_score * 1.1, 1.0), 2)

    return {
        "answer": answer,
        "sources": extracted_sources,
        "confidence": confidence,
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "total_ms": int((time.time() - start) * 1000),
        "chunks_used": len(chunks) or len(extracted_sources),
    }


async def stream_retrieve_and_generate(
    question: str,
    tenant_slug: str,
    top_k: int = None,
    history: List[Dict] = None,
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
