"""
Document Registry — Layer 3 of IntelliRAG retrieval.

Stores AI-generated metadata for every indexed document:
  - summary: 3-5 sentence description of what the document contains
  - topics:  list of key topics/keywords (e.g. ["revenue", "FY2026", "bear case"])
  - entities: named entities (products, people, companies, dates)

On every query:
  1. Search registry by topic overlap → find top matching documents
  2. Pass those document IDs to Qdrant → scoped vector search
  3. Fall back to full search if registry returns nothing
"""
import re
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.services.rag.generation import generate_answer

log = logging.getLogger("intellirag.registry")

# ── DDL ───────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS document_registry (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    collection  TEXT NOT NULL,
    document_id TEXT NOT NULL,
    file_type   TEXT,
    file_path   TEXT,
    summary     TEXT,
    topics      TEXT[],
    entities    TEXT[],
    chunk_count INT DEFAULT 0,
    synced_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (document_id, collection)
)
"""

CREATE_IDX_FILENAME  = "CREATE INDEX IF NOT EXISTS idx_registry_filename   ON document_registry(filename)"
CREATE_IDX_COLLECT   = "CREATE INDEX IF NOT EXISTS idx_registry_collection ON document_registry(collection)"


# ── Schema init ───────────────────────────────────────────────────────────────

async def ensure_registry_table():
    """Create registry table if it doesn't exist. Safe to call multiple times."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(CREATE_TABLE_SQL))
        await db.execute(text(CREATE_IDX_FILENAME))
        await db.execute(text(CREATE_IDX_COLLECT))
        await db.commit()
    log.info("[Registry] Table ready")


# ── AI Metadata Generation ────────────────────────────────────────────────────

async def generate_document_metadata(text_sample: str, filename: str) -> Dict[str, Any]:
    """
    Use Groq to extract summary, topics, and entities from document text.
    Returns dict with keys: summary, topics, entities
    """
    # Use first 3000 chars as representative sample
    sample = text_sample[:3000].strip()

    prompt = f"""Analyze this document and return a JSON object with exactly these fields:
{{
  "summary": "2-4 sentence description of what this document contains and its main purpose",
  "topics": ["list", "of", "10-15", "key", "topics", "keywords", "and", "concepts"],
  "entities": ["list", "of", "named", "entities", "like", "product names", "people", "companies", "dates", "financial terms"]
}}

Document filename: {filename}
Document content sample:
{sample}

Return ONLY the JSON object, no explanation, no markdown."""

    messages = [
        {"role": "system", "content": "You are a document analysis assistant. Return only valid JSON."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = await generate_answer(messages)
        # Strip markdown if present
        clean = re.sub(r"```[a-z]*", "", response).replace("```", "").strip()
        data = json.loads(clean)
        return {
            "summary": str(data.get("summary", ""))[:1000],
            "topics": [str(t).lower().strip() for t in data.get("topics", []) if t][:20],
            "entities": [str(e).lower().strip() for e in data.get("entities", []) if e][:30],
        }
    except Exception as e:
        log.warning(f"[Registry] Metadata generation failed for {filename}: {e}")
        # Fallback: extract basic keywords from filename
        words = re.sub(r'[_\-\.]', ' ', filename.rsplit('.', 1)[0]).lower().split()
        return {
            "summary": f"Document: {filename}",
            "topics": [w for w in words if len(w) > 3],
            "entities": [],
        }


# ── Registry CRUD ─────────────────────────────────────────────────────────────

async def upsert_registry_entry(
    document_id: str,
    filename: str,
    collection: str,
    file_type: str,
    file_path: str,
    chunk_count: int,
    text_sample: str,
):
    """
    Add or update a document in the registry.
    Generates AI metadata if not already present.
    Called after every successful ingest.
    """
    await ensure_registry_table()

    # Check if entry already exists with metadata
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, summary FROM document_registry
            WHERE document_id = :doc_id AND collection = :col
        """), {"doc_id": document_id, "col": collection})
        existing = result.fetchone()

    # Generate metadata (always for new docs, skip if already has summary)
    if existing and existing[1]:
        metadata = None  # Already has metadata, just update chunk count
    else:
        log.info(f"[Registry] Generating metadata for {filename}...")
        metadata = await generate_document_metadata(text_sample, filename)

    async with AsyncSessionLocal() as db:
        if metadata:
            await db.execute(text("""
                INSERT INTO document_registry
                    (id, filename, collection, document_id, file_type, file_path,
                     summary, topics, entities, chunk_count, synced_at)
                VALUES
                    (gen_random_uuid()::text, :filename, :collection, :document_id,
                     :file_type, :file_path, :summary, :topics, :entities,
                     :chunk_count, NOW())
                ON CONFLICT (document_id, collection) DO UPDATE SET
                    filename    = EXCLUDED.filename,
                    chunk_count = EXCLUDED.chunk_count,
                    summary     = EXCLUDED.summary,
                    topics      = EXCLUDED.topics,
                    entities    = EXCLUDED.entities,
                    synced_at   = NOW()
            """), {
                "filename": filename,
                "collection": collection,
                "document_id": document_id,
                "file_type": file_type,
                "file_path": file_path,
                "summary": metadata["summary"],
                "topics": metadata["topics"],
                "entities": metadata["entities"],
                "chunk_count": chunk_count,
            })
        else:
            # Just update chunk count and sync time
            await db.execute(text("""
                UPDATE document_registry
                SET chunk_count = :chunk_count, synced_at = NOW()
                WHERE document_id = :doc_id AND collection = :col
            """), {"chunk_count": chunk_count, "doc_id": document_id, "col": collection})

        await db.commit()

    log.info(f"[Registry] Upserted: {filename} in {collection}")


async def remove_registry_entry(document_id: str, collection: str):
    """Remove a document from the registry when it's deleted."""
    await ensure_registry_table()
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            DELETE FROM document_registry
            WHERE document_id = :doc_id AND collection = :col
        """), {"doc_id": document_id, "col": collection})
        await db.commit()


# ── Registry Search ───────────────────────────────────────────────────────────

async def search_registry(
    query: str,
    collections: List[str],
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    """
    Find the most relevant documents for a query using topic/entity overlap.

    Scoring:
    - Each matching topic → +2 points
    - Each matching entity → +3 points (more specific)
    - Filename keyword match → +5 points (most specific)

    Returns list of {document_id, filename, collection, score, summary}
    sorted by score descending.
    """
    await ensure_registry_table()

    # Extract query keywords for matching
    stop = {"what", "which", "when", "where", "who", "how", "the", "was", "were",
            "did", "does", "show", "give", "tell", "find", "list", "about", "from",
            "with", "that", "this", "please", "can", "you", "for", "and", "are"}
    query_words = set(
        w.lower().strip("?.,!") for w in query.split()
        if len(w) > 2 and w.lower() not in stop
    )

    # Also add bigrams for better matching
    words_list = [w.lower().strip("?.,!") for w in query.split() if len(w) > 2]
    bigrams = {f"{words_list[i]} {words_list[i+1]}" for i in range(len(words_list)-1)}
    query_terms = query_words | bigrams

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT document_id, filename, collection, summary, topics, entities, chunk_count
            FROM document_registry
            WHERE collection = ANY(:collections)
            ORDER BY synced_at DESC
        """), {"collections": collections})
        rows = result.fetchall()

    if not rows:
        return []

    scored = []
    for row in rows:
        doc_id, filename, collection, summary, topics, entities, chunk_count = row
        topics = topics or []
        entities = entities or []
        score = 0

        # Topic overlap
        for topic in topics:
            if any(qt in topic or topic in qt for qt in query_terms):
                score += 2

        # Entity overlap (higher weight — more specific)
        for entity in entities:
            if any(qt in entity or entity in qt for qt in query_terms):
                score += 3

        # Filename match (highest weight — most explicit)
        clean_fn = re.sub(r'[_\-\.]', ' ', filename.rsplit('.', 1)[0]).lower()
        fn_words = set(clean_fn.split())
        filename_matches = len(query_words & fn_words)
        score += filename_matches * 5

        if score > 0:
            scored.append({
                "document_id": doc_id,
                "filename": filename,
                "collection": collection,
                "summary": summary or "",
                "score": score,
                "chunk_count": chunk_count or 0,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── Registry List (for UI) ────────────────────────────────────────────────────

async def list_registry(collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all documents in the registry, optionally filtered by collection."""
    await ensure_registry_table()
    async with AsyncSessionLocal() as db:
        if collection:
            result = await db.execute(text("""
                SELECT id, filename, collection, document_id, file_type,
                       summary, topics, entities, chunk_count, synced_at
                FROM document_registry
                WHERE collection = :col
                ORDER BY synced_at DESC
            """), {"col": collection})
        else:
            result = await db.execute(text("""
                SELECT id, filename, collection, document_id, file_type,
                       summary, topics, entities, chunk_count, synced_at
                FROM document_registry
                ORDER BY synced_at DESC
            """))
        rows = result.fetchall()

    return [
        {
            "id": r[0],
            "filename": r[1],
            "collection": r[2],
            "document_id": r[3],
            "file_type": r[4],
            "summary": r[5],
            "topics": r[6] or [],
            "entities": r[7] or [],
            "chunk_count": r[8] or 0,
            "synced_at": str(r[9]) if r[9] else None,
        }
        for r in rows
    ]
