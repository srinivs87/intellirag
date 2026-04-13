import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List

from app.services.ingestion import ingest_document

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    chunks_created: int
    message: str


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    tenant: str = Form(default="uploaded"),
    uploaded_by: str = Form(default="admin-ui"),
):
    """
    Upload and ingest a document. Stored in intellirag_uploaded collection.
    Searchable via 'Uploaded Docs' source pill in the widget.
    """
    # Validate extension
    from pathlib import Path
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Read file
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    document_id = str(uuid.uuid4())

    try:
        result = await ingest_document(
            file_bytes=file_bytes,
            filename=file.filename,
            tenant_slug=tenant,
            document_id=document_id,
            uploaded_by=uploaded_by,
        )
        return IngestResponse(
            document_id=result["document_id"],
            filename=result["filename"],
            status="ready",
            chunks_created=result["chunks_created"],
            message=f"Successfully ingested {result['chunks_created']} chunks",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/upload-multiple")
async def upload_multiple(
    files: List[UploadFile] = File(...),
    tenant: str = Form(default="uploaded"),
    uploaded_by: str = Form(default="admin-ui"),
):
    """Upload and ingest multiple documents at once."""
    results = []
    for file in files:
        try:
            file_bytes = await file.read()
            document_id = str(uuid.uuid4())
            result = await ingest_document(
                file_bytes=file_bytes,
                filename=file.filename,
                tenant_slug=tenant,
                document_id=document_id,
                uploaded_by=uploaded_by,
            )
            results.append({"filename": file.filename, "status": "success", **result})
        except Exception as e:
            results.append({"filename": file.filename, "status": "failed", "error": str(e)})

    return {"results": results, "total": len(files), "succeeded": sum(1 for r in results if r["status"] == "success")}


@router.get("/documents")
async def list_documents(tenant: str = "uploaded"):
    """List all ingested documents. For 'uploaded', also checks intellirag_general and intellirag_hr."""
    from app.core.vector_store import get_qdrant
    client = get_qdrant()

    # Which collections to query
    if tenant == "uploaded":
        collections_to_check = ["intellirag_uploaded", "intellirag_general", "intellirag_hr"]
    else:
        collections_to_check = [f"intellirag_{tenant}"]

    docs: dict = {}
    try:
        existing = await client.get_collections()
        existing_names = {c.name for c in existing.collections}

        for collection_name in collections_to_check:
            if collection_name not in existing_names:
                continue
            try:
                result = await client.scroll(
                    collection_name=collection_name,
                    limit=2000,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in result[0]:
                    doc_id = point.payload.get("document_id")
                    if not doc_id:
                        continue
                    if doc_id not in docs:
                        docs[doc_id] = {
                            "document_id": doc_id,
                            "filename": point.payload.get("filename", "Unknown"),
                            "uploaded_by": point.payload.get("uploaded_by", "—"),
                            "chunk_count": 0,
                            "collection": collection_name.replace("intellirag_", ""),
                            "web_url": point.payload.get("web_url", ""),
                            "file_path": point.payload.get("file_path", ""),
                            "source_type": point.payload.get("source_type", ""),
                        }
                    docs[doc_id]["chunk_count"] += 1
            except Exception:
                continue
    except Exception:
        pass

    # Enrich with web_url from m365_synced_files for connector files missing it
    docs_needing_url = {d["document_id"]: d for d in docs.values()
                        if not d.get("web_url") and (
                            "m365" in d.get("uploaded_by","") or
                            d.get("collection") in ("sharepoint","teams","onedrive")
                        )}
    if docs_needing_url:
        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import text as sql_text
            async with AsyncSessionLocal() as db:
                for doc_id, doc in docs_needing_url.items():
                    # Try by document_id first
                    r = await db.execute(sql_text("""
                        SELECT web_url, file_path, file_id, source_type
                        FROM m365_synced_files WHERE document_id = :did LIMIT 1
                    """), {"did": doc_id})
                    row = r.fetchone()

                    # Fallback: try by filename (for files synced before document_id was tracked)
                    if not row:
                        r = await db.execute(sql_text("""
                            SELECT web_url, file_path, file_id, source_type
                            FROM m365_synced_files WHERE filename = :fname
                            ORDER BY synced_at DESC LIMIT 1
                        """), {"fname": doc.get("filename","")})
                        row = r.fetchone()

                    if row and doc_id in docs:
                        if row.web_url:
                            docs[doc_id]["web_url"] = row.web_url
                        elif row.file_path and row.file_path.strip():
                            # Construct SharePoint URL from file_path
                            path = row.file_path.strip()
                            if not path.startswith("/"):
                                path = "/" + path
                            col = docs[doc_id].get("collection","")
                        if col == "onedrive":
                            docs[doc_id]["web_url"] = f"https://altencalsoftlabs-my.sharepoint.com/personal{path}"
                        else:
                            docs[doc_id]["web_url"] = f"https://altencalsoftlabs.sharepoint.com{path}"
                        if row.file_path:
                            docs[doc_id]["file_path"] = row.file_path
        except Exception:
            pass

    # Enrich connector files with web_url from m365_synced_files
    need_url = [d for d in docs.values()
                if not d.get("web_url") and (
                    "m365" in d.get("uploaded_by","") or
                    d.get("collection") in ("sharepoint","teams","onedrive")
                )]
    if need_url:
        try:
            from app.core.database import AsyncSessionLocal as _ASL
            from sqlalchemy import text as _t
            async with _ASL() as db:
                for doc in need_url:
                    # Lookup by filename (most reliable for pre-fix synced files)
                    r = await db.execute(_t("""
                        SELECT web_url, file_path FROM m365_synced_files
                        WHERE filename = :fname ORDER BY synced_at DESC LIMIT 1
                    """), {"fname": doc["filename"]})
                    row = r.fetchone()
                    if row:
                        if row.web_url:
                            docs[doc["document_id"]]["web_url"] = row.web_url
                        elif row.file_path:
                            path = row.file_path.strip()
                            if not path.startswith("/"):
                                path = "/" + path
                            src = (row.source_type or doc.get("collection","")).lower()
                            if src == "onedrive":
                                docs[doc["document_id"]]["web_url"] = f"https://altencalsoftlabs-my.sharepoint.com/personal{path}"
                            else:
                                docs[doc["document_id"]]["web_url"] = f"https://altencalsoftlabs.sharepoint.com{path}"
        except Exception:
            pass
    return {"documents": list(docs.values()), "total": len(docs)}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, tenant: str = "uploaded"):
    """Delete all chunks for a document from the vector store."""
    from app.services.ingestion import delete_document_chunks
    try:
        await delete_document_chunks(document_id, tenant)
        return {"status": "deleted", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}/download")
async def download_document(document_id: str, tenant: str = "uploaded"):
    """Serve the original file from MinIO for inline viewing or download."""
    from fastapi.responses import StreamingResponse
    from app.services.storage import get_minio, download_from_minio
    from app.core.config import settings
    import io

    # Find the file in Qdrant to get filename and collection
    from app.core.vector_store import get_qdrant
    client = get_qdrant()

    filename = None
    object_key = None
    collections_to_check = ["intellirag_uploaded", "intellirag_general", "intellirag_hr"] if tenant in ("uploaded", "general") else [f"intellirag_{tenant}"]

    try:
        existing = await client.get_collections()
        existing_names = {c.name for c in existing.collections}
        for col in collections_to_check:
            if col not in existing_names:
                continue
            result = await client.scroll(
                collection_name=col, limit=1000,
                with_payload=True, with_vectors=False,
            )
            for point in result[0]:
                if point.payload.get("document_id") == document_id:
                    filename = point.payload.get("filename")
                    tenant_slug = point.payload.get("tenant_slug", col.replace("intellirag_", ""))
                    object_key = f"{tenant_slug}/{document_id}/{filename}"
                    break
            if filename:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not filename or not object_key:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_bytes = await download_from_minio(object_key)

        # Determine content type
        ext = filename.rsplit('.', 1)[-1].lower()
        content_types = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'txt': 'text/plain',
            'md': 'text/markdown',
        }
        content_type = content_types.get(ext, 'application/octet-stream')

        # PDFs open inline in browser; others force download
        disposition = 'inline' if ext == 'pdf' else f'attachment; filename="{filename}"'

        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=content_type,
            headers={"Content-Disposition": disposition, "Content-Length": str(len(file_bytes))}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found in storage: {str(e)}")
