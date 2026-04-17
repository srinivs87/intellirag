"""
Document Registry API — exposes registry data for the UI.
Allows viewing, rebuilding, and managing indexed document metadata.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.registry import (
    list_registry,
    search_registry,
    remove_registry_entry,
    upsert_registry_entry,
)

log = logging.getLogger("intellirag.registry_api")
router = APIRouter()


@router.get("/api/registry")
async def get_registry(collection: Optional[str] = None):
    """List all documents in the registry."""
    try:
        docs = await list_registry(collection)
        return {"documents": docs, "total": len(docs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/registry/search")
async def search_registry_endpoint(q: str, collection: Optional[str] = None):
    """Search registry by topic/entity overlap."""
    try:
        collections = [collection] if collection else [
            "intellirag_localfs", "intellirag_gdrive",
            "intellirag_uploaded", "intellirag_general",
        ]
        results = await search_registry(q, collections)
        return {"results": results, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RebuildRequest(BaseModel):
    collection: Optional[str] = None


@router.post("/api/registry/rebuild")
async def rebuild_registry(req: RebuildRequest):
    """
    Rebuild registry for all documents in a collection.
    Fetches documents from Qdrant and regenerates AI metadata.
    """
    from app.core.vector_store import get_qdrant
    from app.services.ingestion import parse_document

    client = get_qdrant()
    collection = req.collection or "intellirag_localfs"

    try:
        # Get all unique documents in collection
        result = await client.scroll(
            collection_name=collection,
            limit=1000,
            with_payload=True,
        )
        points = result[0]

        # Group by document_id
        docs: dict = {}
        for point in points:
            doc_id = point.payload.get("document_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "document_id": doc_id,
                    "filename": point.payload.get("filename", ""),
                    "file_path": point.payload.get("file_path", ""),
                    "collection": collection,
                    "chunks": [],
                }
            docs[doc_id]["chunks"].append(point.payload.get("text", ""))

        # Check which docs already have registry entries
        from app.services.registry import ensure_registry_table
        await ensure_registry_table()
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text as sql_text
        async with AsyncSessionLocal() as db:
            result = await db.execute(sql_text(
                "SELECT document_id FROM document_registry WHERE collection = :col"
            ), {"col": collection})
            existing_doc_ids = {row[0] for row in result.fetchall()}

        rebuilt = 0
        for doc_id, doc in docs.items():
            if not doc["filename"]:
                continue
            # Skip if already registered with metadata
            if doc_id in existing_doc_ids:
                log.info(f"[Registry] Skipping {doc['filename']} — already registered")
                continue
            # Use chunks from across the document for better coverage
            # Take first 2 + middle 2 + last 2 chunks for representative sample
            all_chunks = doc["chunks"]
            n = len(all_chunks)
            if n <= 6:
                sample_chunks = all_chunks
            else:
                mid = n // 2
                sample_chunks = all_chunks[:2] + all_chunks[mid:mid+2] + all_chunks[-2:]
            text_sample = "\n\n".join(sample_chunks)
            file_ext = doc["filename"].rsplit(".", 1)[-1].lower() if "." in doc["filename"] else ""
            await upsert_registry_entry(
                document_id=doc_id,
                filename=doc["filename"],
                collection=collection,
                file_type=file_ext,
                file_path=doc["file_path"],
                chunk_count=len(doc["chunks"]),
                text_sample=text_sample,
            )
            rebuilt += 1

        return {"status": "ok", "rebuilt": rebuilt, "collection": collection}

    except Exception as e:
        log.error(f"[Registry] Rebuild failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/registry/{document_id}")
async def delete_registry_entry(document_id: str, collection: str = "intellirag_localfs"):
    """Remove a document from the registry."""
    try:
        await remove_registry_entry(document_id, collection)
        return {"status": "deleted", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateTopicsRequest(BaseModel):
    document_id: str
    collection: str
    extra_topics: list = []
    extra_entities: list = []

@router.post("/api/registry/update-topics")
async def update_registry_topics(req: UpdateTopicsRequest):
    """Manually add topics/entities to a registry entry."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE document_registry
            SET topics   = array(SELECT DISTINCT unnest(topics || :extra_topics)),
                entities = array(SELECT DISTINCT unnest(entities || :extra_entities))
            WHERE document_id = :doc_id AND collection = :col
        """), {
            "extra_topics": req.extra_topics,
            "extra_entities": req.extra_entities,
            "doc_id": req.document_id,
            "col": req.collection,
        })
        await db.commit()
    return {"status": "ok", "document_id": req.document_id}
