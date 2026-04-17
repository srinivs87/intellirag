"""
Retrieval Service — hybrid vector + BM25 + registry-aware search.

Three-layer retrieval:
  Layer 1 — Filename keyword boost: boosts chunks from documents whose
             filename matches query keywords.
  Layer 2 — Source diversity: caps max chunks per document so one
             large file cannot dominate results.
  Layer 3 — Document registry: pre-retrieval step that finds the most
             relevant documents by topic/entity overlap, then scopes
             the Qdrant search to those documents only.
"""
import re
import asyncio
import logging
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi
from qdrant_client.models import Filter, FieldCondition, MatchText, MatchValue

from app.core.config import settings
from app.core.vector_store import get_qdrant
from app.services.embedding import get_embedding

log = logging.getLogger("intellirag.retrieval")

# ── Collection routing ────────────────────────────────────────────────────────

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

# ── Constants ─────────────────────────────────────────────────────────────────

STOP_WORDS = {
    "please", "summarize", "summary", "about", "what", "tell", "give",
    "show", "from", "with", "this", "that", "the", "and", "for", "are",
    "was", "were", "have", "has", "did", "does", "how", "which", "who",
    "when", "where", "find", "get", "list", "explain", "describe",
    "highest", "lowest", "best", "worst", "latest", "recent", "chart",
    "pie", "bar", "graph", "breakdown", "using", "into", "just",
}

FINANCIAL_KEYWORDS = {
    "revenue", "profit", "forecast", "budget", "ebitda", "margin",
    "quarterly", "annual", "fiscal", "fy2025", "fy2026", "bear", "bull",
    "scenario", "growth", "financial", "income", "cash", "balance",
    "investor", "presentation", "report", "dashboard", "client", "initiative",
    "strategic", "strategy", "outlook", "guidance", "segment", "division",
}

FINANCIAL_FILENAMES = {
    "acl_digital", "financial", "investor", "dashboard", "annual", "report",
}

# Known scenario/financial terms for exact keyword fallback
SCENARIO_TERMS = {
    "bear": ["Bear Case", "bear case"],
    "bull": ["Bull Case", "bull case"],
    "base case": ["Base Case", "base case"],
    "scenario": ["FY2026 SCENARIO", "scenario analysis"],
    "strategic": ["Strategic Initiatives", "strategic initiatives"],
    "initiative": ["Strategic Initiatives", "IntelliRAG Platform", "MediAIConnect"],
    "client": ["Client Analytics", "Client Revenue", "YoY Growth", "Entry:"],
    "growth": ["YoY Growth", "highest revenue", "Client Analytics"],
    "highest": ["YoY Growth", "Client Analytics", "highest revenue"],
    "headcount": ["Headcount", "headcount"],
    "nurseconnect": ["NurseConnect", "nurseconnect"],
    "medcore": ["MedCore", "medcore"],
    "startupai": ["StartupAI", "startupai"],
}

JUNK_PATTERNS = [
    "confidential", "all rights reserved", "trademark",
    "property of their", "©", "copyright"
]


# ── Layer 1 — Filename Keyword Boost ─────────────────────────────────────────

def extract_filename_keywords(question: str) -> List[str]:
    """Extract meaningful keywords from query for filename matching."""
    q = re.sub(r'[^\w\s]', ' ', question.lower())
    words = [w for w in q.split() if len(w) > 2 and w not in STOP_WORDS]
    for y in re.findall(r'\b(20\d{2})\b', question):
        if y not in words:
            words.append(y)
    return words


def boost_filename_matches(chunks: List[Dict], keywords: List[str]) -> List[Dict]:
    """
    Layer 1: Boost score of chunks from documents whose filename matches
    query keywords. Financial documents get extra boost on financial queries.
    """
    if not keywords:
        return chunks

    kw_set = set(keywords)
    is_financial = bool(kw_set & FINANCIAL_KEYWORDS)

    boosted = []
    for chunk in chunks:
        filename = chunk.get("filename", "").lower()
        clean_name = re.sub(r'[_\-\.]', ' ', filename.rsplit('.', 1)[0])

        match_count = sum(1 for kw in keywords if kw in clean_name or kw in filename)
        boost = 1.0 + (match_count * 0.5)

        if is_financial and any(f in filename for f in FINANCIAL_FILENAMES):
            boost *= 1.4

        boosted.append({**chunk, "score": chunk["score"] * boost})

    boosted.sort(key=lambda x: x["score"], reverse=True)
    return boosted


# ── Layer 2 — Source Diversity ────────────────────────────────────────────────

def apply_source_diversity(chunks: List[Dict], top_k: int, max_per_doc: int = 3) -> List[Dict]:
    """
    Layer 2: Ensure no single document dominates results.
    Caps chunks per document to max_per_doc using filename as key.
    """
    file_counts: Dict[str, int] = {}
    seen_chunks: set = set()
    diverse: List[Dict] = []

    for chunk in chunks:
        fname = chunk.get("filename", "")
        chunk_key = f"{fname}_{chunk.get('chunk_index', 0)}"
        if chunk_key in seen_chunks:
            continue
        if file_counts.get(fname, 0) < max_per_doc:
            diverse.append(chunk)
            file_counts[fname] = file_counts.get(fname, 0) + 1
            seen_chunks.add(chunk_key)
        if len(diverse) >= top_k:
            break

    return diverse


# ── Junk Filter ───────────────────────────────────────────────────────────────

def filter_junk(chunks: List[Dict]) -> List[Dict]:
    """Remove low-quality chunks like footer text, short snippets."""
    return [
        c for c in chunks
        if (
            len(c.get("text", "").strip()) > 50
            and not any(p in c.get("text", "").lower()[:150] for p in JUNK_PATTERNS)
        )
    ]


# ── Keyword Fallback Search ───────────────────────────────────────────────────

async def keyword_fallback_search(
    question: str,
    collection_name: str,
    query_embedding: List[float],
    existing_ids: set,
    client,
) -> List[Dict]:
    """
    Search Qdrant using exact text match filters for specific terms.
    Catches chunks that semantic search misses (e.g. "Bear Case", "strategic initiatives").
    """
    # Build search phrases from question
    q_words = question.split()
    phrases = []

    # Check known scenario terms first
    q_lower = question.lower()
    for keyword, terms in SCENARIO_TERMS.items():
        if keyword in q_lower:
            phrases.extend(terms)

    # Add adjacent word bigrams
    for i in range(len(q_words) - 1):
        phrases.append(f"{q_words[i]} {q_words[i+1]}")

    # Add individual meaningful words
    phrases.extend([
        w for w in q_words
        if len(w) > 3 and w.lower() not in STOP_WORDS
    ])

    # Deduplicate while preserving order
    seen = set()
    unique_phrases = []
    for p in phrases:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique_phrases.append(p)

    new_chunks = []
    for phrase in unique_phrases[:4]:
        try:
            kw_filter = Filter(must=[
                FieldCondition(key="text", match=MatchText(text=phrase))
            ])
            hits = await client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=3,
                with_payload=True,
                query_filter=kw_filter,
            )
            for r in hits:
                rid = f"{r.payload.get('filename','')}_{r.payload.get('chunk_index',0)}"
                if rid not in existing_ids:
                    new_chunks.append({
                        "text": r.payload["text"],
                        "filename": r.payload.get("filename", "Unknown"),
                        "document_id": r.payload.get("document_id", ""),
                        "chunk_index": r.payload.get("chunk_index", 0),
                        "score": r.score * 1.4,  # boost for exact match
                        "web_url": r.payload.get("web_url", ""),
                        "file_path": r.payload.get("file_path", ""),
                        "source_type": r.payload.get("source_type", ""),
                    })
                    existing_ids.add(rid)
        except Exception:
            pass

    return new_chunks


# ── Main Retrieval ────────────────────────────────────────────────────────────

async def multi_source_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    sources: Optional[List[str]] = None,
    date_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Main retrieval function. Routes across collections and applies all 3 layers.

    Layer 3 (registry) runs first to identify relevant documents.
    Then Layer 1 (filename boost) and Layer 2 (diversity) refine results.
    """
    active_sources = sources or DEFAULT_SOURCES

    # Resolve source names → collection names
    collections: List[str] = []
    for source in active_sources:
        mapped = SOURCE_COLLECTION_MAP.get(source, [f"intellirag_{source}"])
        collections.extend(mapped)
    collections = list(set(collections))

    # Extract filename keywords for Layer 1
    filename_keywords = extract_filename_keywords(question)

    # ── Layer 3: Registry pre-filtering ──────────────────────────────────────
    registry_doc_ids: Optional[List[str]] = None
    try:
        from app.services.registry import search_registry
        registry_hits = await search_registry(question, collections, top_k=5)
        if registry_hits:
            registry_doc_ids = [h["document_id"] for h in registry_hits]
            log.info(f"[Registry] Found {len(registry_hits)} relevant docs: "
                     f"{[h['filename'] for h in registry_hits]}")
    except Exception as e:
        log.warning(f"[Registry] Search failed, using full search: {e}")

    # ── Vector search ─────────────────────────────────────────────────────────
    if len(collections) == 1:
        slug = collections[0].replace("intellirag_", "")
        chunks = await hybrid_retrieve(
            question, slug, top_k * 4,
            date_filter=date_filter,
            filename_keywords=filename_keywords,
            registry_doc_ids=registry_doc_ids,
        )
    else:
        tasks = [
            hybrid_retrieve(
                question, col.replace("intellirag_", ""), top_k * 4,
                date_filter=date_filter,
                filename_keywords=filename_keywords,
                registry_doc_ids=registry_doc_ids,
            )
            for col in collections
        ]
        results_per_source = await asyncio.gather(*tasks, return_exceptions=True)
        chunks = []
        for res in results_per_source:
            if isinstance(res, list):
                chunks.extend(res)

    if not chunks:
        return []

    # Deduplicate
    chunks.sort(key=lambda x: x["score"], reverse=True)
    seen: set = set()
    deduped: List[Dict] = []
    for chunk in chunks:
        key = f"{chunk['filename']}_{chunk['chunk_index']}"
        if key not in seen:
            seen.add(key)
            deduped.append(chunk)

    # Filter junk
    deduped = filter_junk(deduped)

    # Date filter: return directly — date already narrows to specific meeting
    if date_filter:
        return deduped[:top_k]

    # Layer 2: source diversity
    return apply_source_diversity(deduped, top_k)


async def hybrid_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    date_filter: Optional[str] = None,
    filename_keywords: Optional[List[str]] = None,
    registry_doc_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Single-collection hybrid retrieval:
    1. Dense vector search (optionally scoped to registry documents)
    2. BM25 re-ranking
    3. Layer 1 filename boost
    4. Keyword fallback for exact term matching
    """
    collection_name = f"intellirag_{tenant_slug}"
    client = get_qdrant()

    # Verify collection exists
    try:
        cols = await client.get_collections()
        if collection_name not in [c.name for c in cols.collections]:
            return []
    except Exception as e:
        log.warning(f"[Retrieval] get_collections error: {e}")
        return []

    # ── Build Qdrant filter ────────────────────────────────────────────────────
    filter_conditions = []

    # Date filter for meeting queries
    if date_filter:
        try:
            date_prefix = date_filter.split()[0][:10]
            filter_conditions.append(
                FieldCondition(key="file_date", match=MatchText(text=date_prefix))
            )
        except Exception as e:
            log.warning(f"[Retrieval] date_filter error: {e}")

    # Registry scope filter — only search within relevant documents
    # Only apply if registry found documents AND no date filter (date filter is more specific)
    if registry_doc_ids and not date_filter and len(registry_doc_ids) <= 5:
        # Use the top registry document as primary scope
        # Don't over-restrict — take top 3 docs to allow some breadth
        scope_ids = registry_doc_ids[:3]
        # We can't do OR in Qdrant easily, so we'll do a separate search per doc
        # and merge — handled below
        pass  # See scoped search below

    search_filter = Filter(must=filter_conditions) if filter_conditions else None

    # ── Dense vector search ────────────────────────────────────────────────────
    query_embedding = await get_embedding(question)

    # Main search — full collection or date-filtered
    vector_results = await client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        limit=min(top_k * 4, 100),
        with_payload=True,
        query_filter=search_filter,
    )

    # Scoped search — search within registry documents specifically
    scoped_results = []
    if registry_doc_ids and not date_filter:
        for doc_id in registry_doc_ids[:2]:  # Top 2 only to limit Qdrant calls
            try:
                doc_filter = Filter(must=[
                    FieldCondition(key="document_id", match=MatchValue(value=doc_id))
                ])
                hits = await client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding,
                    limit=10,
                    with_payload=True,
                    query_filter=doc_filter,
                )
                scoped_results.extend(hits)
            except Exception:
                pass

    # Merge all results
    all_results = list(vector_results) + scoped_results
    if not all_results:
        return []

    # Deduplicate by point id
    seen_ids = set()
    unique_results = []
    for r in all_results:
        if r.id not in seen_ids:
            seen_ids.add(r.id)
            unique_results.append(r)

    # ── BM25 re-ranking ────────────────────────────────────────────────────────
    candidate_texts = [r.payload["text"] for r in unique_results]
    tokenized = [t.lower().split() for t in candidate_texts]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(question.lower().split())
    max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
    bm25_norm = [s / max_bm25 for s in bm25_scores]

    alpha = settings.HYBRID_ALPHA
    results: List[Dict] = []
    for i, r in enumerate(unique_results):
        hybrid_score = alpha * r.score + (1 - alpha) * bm25_norm[i]
        # Boost scoped (registry) results slightly
        if r in scoped_results and r not in vector_results:
            hybrid_score *= 1.2
        results.append({
            "text": r.payload["text"],
            "filename": r.payload.get("filename", "Unknown"),
            "document_id": r.payload.get("document_id", ""),
            "chunk_index": r.payload.get("chunk_index", 0),
            "score": hybrid_score,
            "web_url": r.payload.get("web_url", ""),
            "file_path": r.payload.get("file_path", ""),
            "source_type": r.payload.get("source_type", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # ── Layer 1: filename keyword boost ───────────────────────────────────────
    if filename_keywords:
        results = boost_filename_matches(results, filename_keywords)

    # ── Keyword fallback: find exact-match chunks ──────────────────────────────
    existing_ids = {f"{r['filename']}_{r['chunk_index']}" for r in results}
    fallback = await keyword_fallback_search(
        question, collection_name, query_embedding, existing_ids, client
    )
    if fallback:
        results.extend(fallback)
        results.sort(key=lambda x: x["score"], reverse=True)

    return results
