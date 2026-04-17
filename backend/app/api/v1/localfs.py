"""
Local File System connector API.

Improvements over original:
  - File hash tracking: never re-index unchanged files
  - Exclude list: admin can permanently exclude files/patterns
  - Smart sync: skips files that haven't changed since last index
  - Clean deletion: removes from Qdrant + registry when file deleted
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.ingestion import ingest_document

log = logging.getLogger("intellirag.localfs")
router = APIRouter()

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv", ".pptx", ".ppt", ".md"}
IGNORE_NAMES = {".DS_Store", "Thumbs.db", "__pycache__", ".git", "node_modules", ".env"}


# ── Ensure tables exist ───────────────────────────────────────────────────────

async def _ensure_tables():
    async with AsyncSessionLocal() as db:
        # Main sync tracking table with hash support
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS localfs_synced_files (
                id          TEXT PRIMARY KEY,
                file_path   TEXT UNIQUE NOT NULL,
                filename    TEXT NOT NULL,
                document_id TEXT NOT NULL,
                tenant_slug TEXT NOT NULL DEFAULT 'general',
                file_date   TEXT,
                file_hash   TEXT,
                hostname    TEXT,
                synced_at   TIMESTAMP DEFAULT NOW()
            )
        """))
        # Add file_hash column if upgrading from old schema
        await db.execute(text("""
            ALTER TABLE localfs_synced_files
            ADD COLUMN IF NOT EXISTS file_hash TEXT
        """))
        # Exclude list table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS localfs_excluded_files (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                pattern     TEXT UNIQUE NOT NULL,
                reason      TEXT,
                excluded_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.commit()


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


def _compute_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


async def _is_excluded(filename: str, file_path: str) -> bool:
    """Check if a file matches any exclusion pattern."""
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT pattern FROM localfs_excluded_files"
        ))
        patterns = [row[0] for row in result.fetchall()]

    filename_lower = filename.lower()
    path_lower = file_path.lower()
    for pattern in patterns:
        p = pattern.lower()
        if p in filename_lower or p in path_lower:
            return True
    return False


async def _get_existing_hash(file_path: str) -> Optional[str]:
    """Get the stored hash for a file path, if it exists."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT file_hash FROM localfs_synced_files WHERE file_path = :fp"
        ), {"fp": file_path})
        row = result.fetchone()
        return row[0] if row else None


# ── Upload endpoint (called by local agent) ───────────────────────────────────

@router.post("/api/ingest/localfs-upload")
async def upload_local_file(
    file: UploadFile = File(...),
    tenant_slug: str = Form("general"),
    source_type: str = Form("localfs"),
    file_path: str = Form(""),
    file_date: Optional[str] = Form(None),
    hostname: Optional[str] = Form(None),
    file_hash: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    await _ensure_tables()
    await _ensure_localfs_collection()

    # Check exclude list
    if await _is_excluded(file.filename, file_path or file.filename):
        log.info(f"[LocalFS] Skipping excluded file: {file.filename}")
        return {"status": "excluded", "filename": file.filename}

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Check if file has changed since last sync
    incoming_hash = file_hash or _compute_hash(content)
    existing_hash = await _get_existing_hash(file_path or file.filename)
    if existing_hash and existing_hash == incoming_hash:
        log.info(f"[LocalFS] Skipping unchanged file: {file.filename}")
        return {"status": "unchanged", "filename": file.filename}

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
                INSERT INTO localfs_synced_files
                    (id, file_path, filename, document_id, tenant_slug,
                     file_date, file_hash, hostname, synced_at)
                VALUES
                    (:id, :file_path, :filename, :document_id, :tenant_slug,
                     :file_date, :file_hash, :hostname, NOW())
                ON CONFLICT (file_path) DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    filename    = EXCLUDED.filename,
                    file_date   = EXCLUDED.file_date,
                    file_hash   = EXCLUDED.file_hash,
                    synced_at   = NOW()
            """), {
                "id": str(uuid.uuid4()),
                "file_path": file_path or file.filename,
                "filename": file.filename,
                "document_id": document_id,
                "tenant_slug": tenant_slug,
                "file_date": file_date,
                "file_hash": incoming_hash,
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


# ── Delete endpoint ───────────────────────────────────────────────────────────

@router.delete("/api/ingest/localfs")
async def delete_local_file(payload: dict):
    file_path = payload.get("file_path", "")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path required")

    await _ensure_tables()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT document_id FROM localfs_synced_files WHERE file_path = :fp
            """), {"fp": file_path})
            row = result.fetchone()
            if not row:
                return {"status": "not_found"}

            doc_id = row[0]

        # Remove from Qdrant
        from app.core.vector_store import get_qdrant
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = get_qdrant()
        await client.delete(
            collection_name="intellirag_localfs",
            points_selector=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=doc_id))
            ])
        )

        # Remove from registry
        try:
            from app.services.registry import remove_registry_entry
            await remove_registry_entry(doc_id, "intellirag_localfs")
        except Exception:
            pass

        # Remove from sync table
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM localfs_synced_files WHERE file_path = :fp"
            ), {"fp": file_path})
            await db.commit()

        return {"status": "deleted", "document_id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Status endpoint ───────────────────────────────────────────────────────────

@router.get("/api/connectors/localfs/status")
async def localfs_status():
    await _ensure_tables()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(
                "SELECT COUNT(*), MAX(synced_at) FROM localfs_synced_files"
            ))
            row = result.fetchone()
            count = row[0] if row else 0
            last_sync = row[1] if row else None
        return {
            "status": "active",
            "files_indexed": count,
            "last_sync": str(last_sync) if last_sync else None,
        }
    except Exception:
        return {"status": "not_configured", "files_indexed": 0}


# ── Scan endpoint ─────────────────────────────────────────────────────────────

class ScanReq(BaseModel):
    folders: list
    os: str = "mac"

@router.post("/api/ingest/localfs-scan")
async def scan_local_folders(req: ScanReq):
    """
    Scan folders and return list of files.
    Automatically filters excluded files and unsupported formats.
    """
    await _ensure_tables()

    # Load exclude patterns
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT pattern FROM localfs_excluded_files"
        ))
        exclude_patterns = [row[0].lower() for row in result.fetchall()]

    found = []
    for folder in req.folders:
        folder = os.path.expandvars(os.path.expanduser(folder))
        if not os.path.exists(folder):
            continue
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORE_NAMES]
            for fname in files:
                if fname.startswith(".") or fname.startswith("~$"):
                    continue
                import pathlib
                if pathlib.Path(fname).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                # Check exclude patterns
                full_path = os.path.join(root, fname)
                fname_lower = fname.lower()
                path_lower = full_path.lower()
                excluded = any(p in fname_lower or p in path_lower for p in exclude_patterns)
                if not excluded:
                    found.append(full_path)

    return {"files": found, "count": len(found)}


# ── Single file sync ──────────────────────────────────────────────────────────

class SyncFileReq(BaseModel):
    file_path: str
    os: str = "mac"
    force: bool = False  # Force re-index even if unchanged

@router.post("/api/ingest/localfs-sync-file")
async def sync_single_file(req: SyncFileReq):
    import mimetypes
    import pathlib

    await _ensure_tables()

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

    # Check exclude list
    if await _is_excluded(filename, file_path):
        return {"status": "excluded", "filename": filename}

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {file_path}")

    # Hash check — skip if unchanged and not forced
    incoming_hash = _compute_hash(file_bytes)
    if not req.force:
        existing_hash = await _get_existing_hash(file_path)
        if existing_hash and existing_hash == incoming_hash:
            return {"status": "unchanged", "filename": filename}

    await _ensure_localfs_collection()

    document_id = str(uuid.uuid4())
    file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
    hostname = os.uname().nodename if hasattr(os, "uname") else "unknown"

    result = await ingest_document(
        file_bytes=file_bytes,
        filename=filename,
        tenant_slug="general",
        document_id=document_id,
        uploaded_by=f"localfs_ui:{hostname}",
        collection_name="intellirag_localfs",
        extra_metadata={
            "source_type": "localfs",
            "file_path": file_path,
            "hostname": hostname,
            "file_date": file_date,
        },
    )

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO localfs_synced_files
                (id, file_path, filename, document_id, tenant_slug,
                 file_date, file_hash, hostname, synced_at)
            VALUES
                (:id, :fp, :fn, :did, 'general', :fd, :fh, :hn, NOW())
            ON CONFLICT (file_path) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                file_hash   = EXCLUDED.file_hash,
                synced_at   = NOW()
        """), {
            "id": str(uuid.uuid4()),
            "fp": file_path,
            "fn": filename,
            "did": document_id,
            "fd": file_date,
            "fh": incoming_hash,
            "hn": hostname,
        })
        await db.commit()

    return {"status": "ok", "filename": filename, "chunks": result["chunks_created"]}


# ── Mac home path helper ──────────────────────────────────────────────────────

@router.get("/api/ingest/localfs-home")
async def get_mac_home():
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


# ── Exclude list management ───────────────────────────────────────────────────

class ExcludeReq(BaseModel):
    pattern: str
    reason: Optional[str] = None

@router.post("/api/ingest/localfs-exclude")
async def add_exclude_pattern(req: ExcludeReq):
    """Add a filename pattern to the permanent exclude list."""
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO localfs_excluded_files (pattern, reason)
            VALUES (:pattern, :reason)
            ON CONFLICT (pattern) DO NOTHING
        """), {"pattern": req.pattern.lower(), "reason": req.reason})
        await db.commit()
    log.info(f"[LocalFS] Added exclude pattern: {req.pattern}")
    return {"status": "ok", "pattern": req.pattern}


@router.delete("/api/ingest/localfs-exclude/{pattern}")
async def remove_exclude_pattern(pattern: str):
    """Remove a pattern from the exclude list."""
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "DELETE FROM localfs_excluded_files WHERE pattern = :p"
        ), {"p": pattern.lower()})
        await db.commit()
    return {"status": "ok", "pattern": pattern}


@router.get("/api/ingest/localfs-exclude")
async def list_exclude_patterns():
    """List all exclude patterns."""
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT pattern, reason, excluded_at FROM localfs_excluded_files ORDER BY excluded_at DESC"
        ))
        rows = result.fetchall()
    return {
        "patterns": [
            {"pattern": r[0], "reason": r[1], "excluded_at": str(r[2])}
            for r in rows
        ]
    }


@router.get("/api/ingest/localfs-files")
async def list_synced_files():
    """List all synced files with their sync status."""
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT filename, file_path, document_id, file_date, synced_at
            FROM localfs_synced_files
            ORDER BY synced_at DESC
        """))
        rows = result.fetchall()
    return {
        "files": [
            {
                "filename": r[0],
                "file_path": r[1],
                "document_id": r[2],
                "file_date": r[3],
                "synced_at": str(r[4]),
            }
            for r in rows
        ],
        "total": len(rows),
    }
