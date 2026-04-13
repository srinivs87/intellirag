import os
"""
Local File System connector API
Receives files pushed by the IntelliRAG agent running on user machines.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.ingestion import ingest_document

log = logging.getLogger("intellirag.localfs")
router = APIRouter()


async def _ensure_localfs_collection():
    from app.core.vector_store import get_qdrant
    from qdrant_client.models import Distance, VectorParams
    client = get_qdrant()
    try:
        await client.get_collection("intellirag_localfs")
    except Exception:
        await client.create_collection(
            collection_name="intellirag_localfs",
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )


@router.post("/api/ingest/localfs-upload")
async def upload_local_file(
    file: UploadFile = File(...),
    tenant_slug: str = Form("general"),
    source_type: str = Form("localfs"),
    file_path: str = Form(""),
    file_date: Optional[str] = Form(None),
    hostname: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    await _ensure_localfs_collection()

    document_id = str(uuid.uuid4())
    extra_metadata = {
        "source_type": "localfs",
        "file_path": file_path or file.filename,
        "hostname": hostname or "unknown",
    }
    if file_date:
        extra_metadata["file_date"] = file_date

    try:
        result = await ingest_document(
            file_bytes=content,
            filename=file.filename,
            tenant_slug=tenant_slug,
            document_id=document_id,
            uploaded_by=f"localfs_agent:{hostname or 'unknown'}",
            collection_name="intellirag_localfs",
            extra_metadata=extra_metadata,
        )

        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS localfs_synced_files (
                    id TEXT PRIMARY KEY,
                    file_path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    tenant_slug TEXT NOT NULL DEFAULT 'general',
                    file_date TEXT,
                    hostname TEXT,
                    synced_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await db.execute(text("""
                INSERT INTO localfs_synced_files
                    (id, file_path, filename, document_id, tenant_slug, file_date, hostname, synced_at)
                VALUES
                    (:id, :file_path, :filename, :document_id, :tenant_slug, :file_date, :hostname, NOW())
                ON CONFLICT (file_path) DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    filename    = EXCLUDED.filename,
                    file_date   = EXCLUDED.file_date,
                    synced_at   = NOW()
            """), {
                "id": str(uuid.uuid4()),
                "file_path": file_path or file.filename,
                "filename": file.filename,
                "document_id": document_id,
                "tenant_slug": tenant_slug,
                "file_date": file_date,
                "hostname": hostname,
            })
            await db.commit()

        log.info(f"[LocalFS] Indexed: {file.filename} ({result['chunks_created']} chunks)")
        return {
            "status": "ok",
            "document_id": document_id,
            "filename": file.filename,
            "chunks": result["chunks_created"],
        }

    except Exception as e:
        log.error(f"[LocalFS] Error indexing {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/ingest/localfs")
async def delete_local_file(payload: dict):
    file_path = payload.get("file_path", "")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path required")

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT document_id FROM localfs_synced_files WHERE file_path = :fp
            """), {"fp": file_path})
            row = result.fetchone()
            if not row:
                return {"status": "not_found"}

            from app.core.vector_store import get_qdrant
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            client = get_qdrant()
            await client.delete(
                collection_name="intellirag_localfs",
                points_selector=Filter(must=[
                    FieldCondition(key="document_id", match=MatchValue(value=row[0]))
                ])
            )
            await db.execute(text(
                "DELETE FROM localfs_synced_files WHERE file_path = :fp"
            ), {"fp": file_path})
            await db.commit()

        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/connectors/localfs/status")
async def localfs_status():
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(
                "SELECT COUNT(*), MAX(synced_at) FROM localfs_synced_files"
            ))
            row = result.fetchone()
            count = row[0] if row else 0
            last_sync = row[1] if row else None
        return {"status": "active", "files_indexed": count, "last_sync": str(last_sync) if last_sync else None}
    except Exception:
        return {"status": "not_configured", "files_indexed": 0}


from pydantic import BaseModel as _BM

class _ScanReq(_BM):
    folders: list
    os: str = "mac"

class _SyncFileReq(_BM):
    file_path: str
    os: str = "mac"

@router.post("/api/ingest/localfs-scan")
async def scan_local_folders(req: _ScanReq):
    from pathlib import Path
    SUPPORTED = {".pdf",".docx",".doc",".xlsx",".xls",".txt",".csv",".pptx"}
    IGNORE = {".DS_Store","Thumbs.db","__pycache__",".git","node_modules"}
    found = []
    for folder in req.folders:
        folder = os.path.expandvars(os.path.expanduser(folder))
        if not os.path.exists(folder): continue
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORE]
            for fname in files:
                if fname.startswith(".") or fname.startswith("~$"): continue
                if Path(fname).suffix.lower() in SUPPORTED:
                    found.append(os.path.join(root, fname))
    return {"files": found, "count": len(found)}

@router.post("/api/ingest/localfs-sync-file")
async def sync_single_file(req: _SyncFileReq):
    import mimetypes
    from pathlib import Path
    # Resolve Mac ~ paths inside Docker
    def _resolve(p):
        if p.startswith("~/") or p == "~":
            users_dir = "/Users"
            if os.path.exists(users_dir):
                user_dirs = [d for d in os.listdir(users_dir)
                             if not d.startswith(".") and os.path.isdir(os.path.join(users_dir, d))]
                if user_dirs:
                    return p.replace("~", os.path.join(users_dir, user_dirs[0]), 1)
        return os.path.expandvars(p)
    file_path = _resolve(req.file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {file_path}")
    await _ensure_localfs_collection()
    document_id = str(uuid.uuid4())
    file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
    hostname = os.uname().nodename if hasattr(os, "uname") else "unknown"
    result = await ingest_document(
        file_bytes=file_bytes, filename=filename, tenant_slug="general",
        document_id=document_id, uploaded_by=f"localfs_ui:{hostname}",
        collection_name="intellirag_localfs",
        extra_metadata={"source_type":"localfs","file_path":file_path,"hostname":hostname,"file_date":file_date},
    )
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS localfs_synced_files (
                id TEXT PRIMARY KEY, file_path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL, document_id TEXT NOT NULL,
                tenant_slug TEXT NOT NULL DEFAULT 'general',
                file_date TEXT, hostname TEXT, synced_at TIMESTAMP DEFAULT NOW()
            )"""))
        await db.execute(text("""
            INSERT INTO localfs_synced_files (id,file_path,filename,document_id,tenant_slug,file_date,hostname,synced_at)
            VALUES (:id,:fp,:fn,:did,'general',:fd,:hn,NOW())
            ON CONFLICT (file_path) DO UPDATE SET document_id=EXCLUDED.document_id,synced_at=NOW()
        """), {"id":str(uuid.uuid4()),"fp":file_path,"fn":filename,"did":document_id,"fd":file_date,"hn":hostname})
        await db.commit()
    return {"status":"ok","filename":filename,"chunks":result["chunks_created"]}


@router.get("/api/ingest/localfs-home")
async def get_mac_home():
    """Returns the Mac home directory as seen from Docker."""
    users_dir = "/Users"
    if os.path.exists(users_dir):
        user_dirs = sorted([
            d for d in os.listdir(users_dir)
            if not d.startswith(".") and d != "Shared"
            and os.path.isdir(os.path.join(users_dir, d))
        ])
        if user_dirs:
            return {"home": f"/Users/{user_dirs[0]}", "username": user_dirs[0]}
    return {"home": os.path.expanduser("~"), "username": "user"}
