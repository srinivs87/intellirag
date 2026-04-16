"""
Retrieval Service — hybrid vector + BM25 search across multiple Qdrant collections.

Improvements:
  Layer 1 — Filename keyword boost: when query mentions a specific document name,
             chunks from that document get a score boost, pushing them to the top.
  Layer 2 — Source diversity: caps max chunks per document so one large file
             cannot dominate the results.
"""
import re
import asyncio
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi
from qdrant_client.models import Filter, FieldCondition, MatchText

from app.core.config import settings
from app.core.vector_store import get_qdrant
from app.services.embedding import get_embedding

SOURCE_COLLECTION_MAP: Dict[str, List[str]] = {
    "uploaded":   ["intellirag_uploaded", "intellirag_general", "intellirag_hr"],
    "gdrive":     ["intellirag_gdrive"],
    "teams":      ["intellirag_teams"],
    "onedrive":   ["intellirag_onedrive"],
    "sharepoint": ["intellirag_sharepoint"],
    "general":    ["intellirag_general"],
    "localfs":    ["intellirag_localfs"],
    "hr":         ["intellirag_hr"],
}

DEFAULT_SOURCES = ["uploaded", "gdrive", "teams", "onedrive", "sharepoint"]

STOP_WORDS = {
    "please", "summarize", "summary", "about", "what", "tell", "give",
    "show", "from", "with", "this", "that", "the", "and", "for", "are",
    "was", "were", "have", "has", "did", "does", "how", "which", "who",
    "when", "where", "find", "get", "list", "explain", "describe",
    "highest", "lowest", "best", "worst", "latest", "recent", "chart",
    "pie", "bar", "graph", "breakdown", "using", "into", "just",
}

# Financial terms that should boost financial documents
FINANCIAL_KEYWORDS = {
    "revenue", "profit", "forecast", "budget", "ebitda", "margin",
    "quarterly", "annual", "fiscal", "fy2025", "fy2026", "bear", "bull",
    "scenario", "growth", "financial", "income", "cash", "balance",
    "investor", "presentation", "report", "dashboard", "client"
}


# ── Layer 1 — Filename Keyword Boost ─────────────────────────────────────────

def extract_filename_keywords(question: str) -> List[str]:
    """Extract keywords from query that likely refer to specific documents."""
    q = re.sub(r'[^\w\s]', ' ', question.lower())
    words = [w for w in q.split() if len(w) > 2 and w not in STOP_WORDS]
    # Always include years
    for y in re.findall(r'\b(20\d{2})\b', question):
        if y not in words:
            words.append(y)
    return words


def boost_filename_matches(chunks: List[Dict], keywords: List[str]) -> List[Dict]:
    """
    Layer 1: Boost score of chunks whose filename matches query keywords.
    Also boosts financial documents when financial keywords are detected.
    """
    if not keywords:
        return chunks

    kw_set = set(keywords)
    is_financial_query = bool(kw_set & FINANCIAL_KEYWORDS)

    financial_filenames = {"acl_digital", "financial", "investor", "dashboard", "annual", "report"}

    boosted = []
    for chunk in chunks:
        filename = chunk.get("filename", "").lower()
        clean_name = re.sub(r'[_\-\.]', ' ', filename.rsplit('.', 1)[0])

        # Filename keyword match boost
        match_count = sum(1 for kw in keywords if kw in clean_name or kw in filename)
        boost = 1.0 + (match_count * 0.5)

        # Extra boost for financial documents on financial queries
        if is_financial_query:
            is_financial_doc = any(f in filename for f in financial_filenames)
            if is_financial_doc:
                boost *= 1.5  # 50% extra boost for financial docs on financial queries

        boosted.append({**chunk, "score": chunk["score"] * boost})

    boosted.sort(key=lambda x: x["score"], reverse=True)
    return boosted


# ── Layer 2 — Source Diversity Cap ───────────────────────────────────────────

def apply_source_diversity(chunks: List[Dict], top_k: int, max_per_doc: int = 1) -> List[Dict]:
    """
    Layer 2: Cap chunks per document to prevent one large file dominating results.

    First pass: take up to max_per_doc best chunks per document.
    Second pass: fill remaining slots if top_k not reached.
    """
    file_counts: Dict[str, int] = {}
    seen_chunks: set = set()
    diverse: List[Dict] = []

    # Single pass — strict max_per_doc per filename, no second pass
    for chunk in chunks:
        fname = chunk.get("filename", "")
        chunk_key = f"{chunk.get('filename','')}_{chunk.get('chunk_index',0)}"
        if chunk_key in seen_chunks:
            continue
        if file_counts.get(fname, 0) < max_per_doc:
            diverse.append(chunk)
            file_counts[fname] = file_counts.get(fname, 0) + 1
            seen_chunks.add(chunk_key)
        if len(diverse) >= top_k:
            break
    return diverse


# ── Main Retrieval ────────────────────────────────────────────────────────────

async def multi_source_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    sources: Optional[List[str]] = None,
    date_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Route retrieval across Qdrant collections in parallel.
    Applies Layer 1 (filename boost) and Layer 2 (source diversity).
    """
    active_sources = sources or DEFAULT_SOURCES

    collections: List[str] = []
    for source in active_sources:
        mapped = SOURCE_COLLECTION_MAP.get(source, [f"intellirag_{source}"])
        collections.extend(mapped)
    collections = list(set(collections))

    # Extract filename keywords once for Layer 1
    filename_keywords = extract_filename_keywords(question)

    if len(collections) == 1:
        slug = collections[0].replace("intellirag_", "")
        chunks = await hybrid_retrieve(
            question, slug, top_k * 3,
            date_filter=date_filter,
            filename_keywords=filename_keywords,
        )
        # Filter out junk chunks
        junk_patterns = ['confidential', 'all rights reserved', 'trademark', 'property of their']
        chunks = [c for c in chunks if (
            len(c.get('text','').strip()) > 50 and
            not any(p in c.get('text','').lower()[:100] for p in junk_patterns)
        )]
        # Date filter active — return directly, date already narrows results
        if date_filter:
            return chunks[:top_k]
        # Apply source diversity for non-date queries
        result = apply_source_diversity(chunks, top_k)
        return result

    # Parallel search
    tasks = [
        hybrid_retrieve(
            question, col.replace("intellirag_", ""), top_k * 3,
            date_filter=date_filter,
            filename_keywords=filename_keywords,
        )
        for col in collections
    ]
    results_per_source = await asyncio.gather(*tasks, return_exceptions=True)

    all_chunks: List[Dict] = []
    for res in results_per_source:
        if isinstance(res, list):
            all_chunks.extend(res)

    if not all_chunks:
        return []

    # Deduplicate
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    seen: set = set()
    deduped: List[Dict] = []
    for chunk in all_chunks:
        key = f"{chunk['document_id']}_{chunk['chunk_index']}"
        if key not in seen:
            seen.add(key)
            deduped.append(chunk)

    # Layer 2 — source diversity
    if date_filter:
        return deduped[:top_k]
    result = apply_source_diversity(deduped, top_k)
    return result


async def hybrid_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    date_filter: Optional[str] = None,
    filename_keywords: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: dense vector search + BM25 re-ranking + Layer 1 filename boost.
    """
    collection_name = f"intellirag_{tenant_slug}"
    client = get_qdrant()

    try:
        collections = await client.get_collections()
        names = [c.name for c in collections.collections]
        if collection_name not in names:
            return []
    except Exception as e:
        print(f"[Retrieval] get_collections error: {e!r}")
        return []

    # Date filter
    search_filter: Optional[Filter] = None
    if date_filter:
        try:
            date_prefix = date_filter.split()[0][:10]
            search_filter = Filter(must=[FieldCondition(
                key="file_date",
                match=MatchText(text=date_prefix),
            )])
        except Exception as e:
            print(f"[Retrieval] date_filter error: {e!r}")

    # Dense vector search — fetch extra for re-ranking
    query_embedding = await get_embedding(question)
    vector_results = await client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        limit=min(top_k * 8, 100),  # fetch many candidates for diversity
        with_payload=True,
        query_filter=search_filter,
    )

    if not vector_results:
        return []

    # BM25 re-ranking
    candidate_texts = [r.payload["text"] for r in vector_results]
    tokenized = [t.lower().split() for t in candidate_texts]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(question.lower().split())
    max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
    bm25_norm = [s / max_bm25 for s in bm25_scores]

    alpha = settings.HYBRID_ALPHA
    results: List[Dict] = []
    for i, result in enumerate(vector_results):
        hybrid_score = alpha * result.score + (1 - alpha) * bm25_norm[i]
        results.append({
            "text": result.payload["text"],
            "filename": result.payload.get("filename", "Unknown"),
            "document_id": result.payload.get("document_id", ""),
            "chunk_index": result.payload.get("chunk_index", 0),
            "score": hybrid_score,
            "web_url": result.payload.get("web_url", ""),
            "file_path": result.payload.get("file_path", ""),
            "source_type": result.payload.get("source_type", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Layer 1 — filename keyword boost
    if filename_keywords:
        results = boost_filename_matches(results, filename_keywords)

    # Exact text keyword fallback — find chunks containing specific query words
    # Uses adjacent word pairs for precision (e.g. "bear case", "revenue forecast")
    words = [w for w in question.split()
             if len(w) > 2 and w.lower() not in {
                 "what", "show", "give", "tell", "from", "with", "that",
                 "this", "about", "please", "find"
             }]
    # Build bigrams first, then unigrams
    # Also add known financial scenario terms
    extra_phrases = []
    q_lower = question.lower()
    if "bear" in q_lower: extra_phrases.append("Bear Case")
    if "bull" in q_lower: extra_phrases.append("Bull Case")
    if "base case" in q_lower: extra_phrases.append("Base Case")
    if "scenario" in q_lower: extra_phrases.append("FY2026 SCENARIO")
    phrases = extra_phrases + [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)] + words
    # Only search for phrases not already well-represented
    existing_ids = {f"{r['filename']}_{r['chunk_index']}" for r in results}
    for phrase in phrases[:4]:
        try:
            kw_filter = Filter(must=[FieldCondition(key="text", match=MatchText(text=phrase))])
            kw_hits = await client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=3,
                with_payload=True,
                query_filter=kw_filter,
            )
            for r in kw_hits:
                rid = f"{r.payload.get('filename','')}_{r.payload.get('chunk_index',0)}"
                if rid not in existing_ids:
                    chunk = {
                        "text": r.payload["text"],
                        "filename": r.payload.get("filename", "Unknown"),
                        "document_id": r.payload.get("document_id", ""),
                        "chunk_index": r.payload.get("chunk_index", 0),
                        "score": r.score * 1.3,
                        "web_url": r.payload.get("web_url", ""),
                        "file_path": r.payload.get("file_path", ""),
                        "source_type": r.payload.get("source_type", ""),
                    }
                    results.append(chunk)
                    existing_ids.add(rid)
        except Exception:
            pass

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
