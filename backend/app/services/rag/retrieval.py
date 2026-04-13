"""
Retrieval Service — hybrid vector + BM25 search across multiple Qdrant collections.
"""
import asyncio
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi
from qdrant_client.models import Filter, FieldCondition, MatchText

from app.core.config import settings
from app.core.vector_store import get_qdrant
from app.services.embedding import get_embedding

# Maps logical source names to Qdrant collection names
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


async def multi_source_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    sources: Optional[List[str]] = None,
    date_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Route retrieval to one or multiple Qdrant collections in parallel.
    Merges and re-ranks results using hybrid scoring.
    """
    active_sources = sources or DEFAULT_SOURCES

    # Resolve source names → collection names
    collections: List[str] = []
    for source in active_sources:
        mapped = SOURCE_COLLECTION_MAP.get(source, [f"intellirag_{source}"])
        collections.extend(mapped)
    collections = list(set(collections))

    if len(collections) == 1:
        slug = collections[0].replace("intellirag_", "")
        return await hybrid_retrieve(question, slug, top_k, date_filter=date_filter)

    # Parallel search across collections
    tasks = [
        hybrid_retrieve(question, col.replace("intellirag_", ""), top_k, date_filter=date_filter)
        for col in collections
    ]
    results_per_source = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge, deduplicate, and re-rank
    all_chunks: List[Dict] = []
    for res in results_per_source:
        if isinstance(res, list):
            all_chunks.extend(res)

    if not all_chunks:
        return []

    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    seen: set = set()
    deduped: List[Dict] = []
    for chunk in all_chunks:
        key = f"{chunk['document_id']}_{chunk['chunk_index']}"
        if key not in seen:
            seen.add(key)
            deduped.append(chunk)

    return deduped[:top_k]


async def hybrid_retrieve(
    question: str,
    tenant_slug: str,
    top_k: int,
    date_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: combines dense vector search with sparse BM25 re-ranking.
    Optionally applies a date filter on the file_date payload field.
    """
    collection_name = f"intellirag_{tenant_slug}"
    client = get_qdrant()

    # Verify collection exists
    try:
        collections = await client.get_collections()
        names = [c.name for c in collections.collections]
        if collection_name not in names:
            return []
    except Exception as e:
        print(f"[Retrieval] get_collections error: {e!r}")
        return []

    # Build optional date filter
    search_filter: Optional[Filter] = None
    if date_filter:
        try:
            date_prefix = date_filter.split()[0][:10]  # YYYY-MM-DD
            search_filter = Filter(must=[FieldCondition(
                key="file_date",
                match=MatchText(text=date_prefix),
            )])
        except Exception as e:
            print(f"[Retrieval] date_filter build error: {e!r}")

    # Dense vector search
    query_embedding = await get_embedding(question)
    vector_results = await client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        limit=top_k * 2,
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
    return results[:top_k]
