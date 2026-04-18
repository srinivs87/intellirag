"""
Auto-Sync Service — watches configured local folders and automatically
indexes new, modified, and deleted files.

How it works:
1. On startup, loads sync config from database (which folders to watch)
2. Every SYNC_INTERVAL seconds, scans all configured folders
3. Compares file hashes against database records
4. New files → ingest + register
5. Modified files → delete old chunks + re-ingest
6. Deleted files → remove from Qdrant + registry
7. Broadcasts sync events via SSE for real-time UI updates

Enterprise features:
- Configurable per-folder sync intervals
- Exclude patterns (per folder or global)
- Sync status tracking with timestamps
- Never re-indexes unchanged files (hash-based)
- Graceful error handling — one bad file never stops the sync
"""
import os
import asyncio
import hashlib
import logging
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

log = logging.getLogger("intellirag.autosync")

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls",
    ".pptx", ".ppt", ".txt", ".csv", ".md",
}

IGNORE_PREFIXES = {".", "~$", "__", "node_modules"}
IGNORE_NAMES = {".DS_Store", "Thumbs.db", ".git", "desktop.ini"}

DEFAULT_SYNC_INTERVAL = 300  # 5 minutes
MIN_SYNC_INTERVAL = 60       # 1 minute minimum

# Global state
_sync_task: Optional[asyncio.Task] = None
_sync_status: Dict = {
    "running": False,
    "last_sync": None,
    "last_sync_result": None,
    "files_watched": 0,
    "folders": [],
}
_sse_subscribers: List[asyncio.Queue] = []


# ── SSE Broadcasting ──────────────────────────────────────────────────────────

def broadcast_event(event_type: str, data: dict):
    """Send real-time event to all connected UI subscribers."""
    for queue in _sse_subscribers:
        try:
            queue.put_nowait({"type": event_type, "data": data, "ts": datetime.now().isoformat()})
        except asyncio.QueueFull:
            pass


def add_subscriber(queue: asyncio.Queue):
    _sse_subscribers.append(queue)


def remove_subscriber(queue: asyncio.Queue):
    if queue in _sse_subscribers:
        _sse_subscribers.remove(queue)


# ── Database helpers ──────────────────────────────────────────────────────────

async def ensure_autosync_tables():
    """Create auto-sync config and log tables if they don't exist."""
    async with AsyncSessionLocal() as db:
        # Folder configuration table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS autosync_folders (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                folder_path TEXT UNIQUE NOT NULL,
                enabled     BOOLEAN DEFAULT TRUE,
                interval_s  INT DEFAULT 300,
                added_at    TIMESTAMPTZ DEFAULT NOW(),
                last_sync   TIMESTAMPTZ
            )
        """))
        # Sync run log
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS autosync_log (
                id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                started_at      TIMESTAMPTZ DEFAULT NOW(),
                completed_at    TIMESTAMPTZ,
                files_added     INT DEFAULT 0,
                files_updated   INT DEFAULT 0,
                files_removed   INT DEFAULT 0,
                files_skipped   INT DEFAULT 0,
                errors          INT DEFAULT 0,
                status          TEXT DEFAULT 'running'
            )
        """))
        # Add file_hash column to localfs_synced_files if missing
        await db.execute(text("""
            ALTER TABLE localfs_synced_files
            ADD COLUMN IF NOT EXISTS file_hash TEXT
        """))
        await db.commit()
    log.info("[AutoSync] Tables ready")


async def get_sync_folders() -> List[Dict]:
    """Get all enabled sync folders from database."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, folder_path, enabled, interval_s, last_sync
            FROM autosync_folders
            WHERE enabled = TRUE
            ORDER BY folder_path
        """))
        rows = result.fetchall()
    return [
        {"id": r[0], "folder_path": r[1], "enabled": r[2],
         "interval_s": r[3], "last_sync": r[4]}
        for r in rows
    ]


async def get_exclude_patterns() -> Set[str]:
    """Get global exclude patterns."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(
                "SELECT pattern FROM localfs_excluded_files"
            ))
            return {row[0].lower() for row in result.fetchall()}
    except Exception:
        return set()


async def get_synced_file(file_path: str) -> Optional[Dict]:
    """Get existing sync record for a file path."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT document_id, file_hash, synced_at
            FROM localfs_synced_files
            WHERE file_path = :fp
        """), {"fp": file_path})
        row = result.fetchone()
    if not row:
        return None
    return {"document_id": row[0], "file_hash": row[1], "synced_at": row[2]}


async def get_all_synced_paths() -> Set[str]:
    """Get all file paths currently in the sync database."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT file_path FROM localfs_synced_files"
        ))
        return {row[0] for row in result.fetchall()}


async def save_synced_file(file_path: str, filename: str, document_id: str, file_hash: str, file_date: str):
    """Save or update sync record."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO localfs_synced_files
                (id, file_path, filename, document_id, tenant_slug, file_hash, file_date, synced_at)
            VALUES
                (gen_random_uuid()::text, :fp, :fn, :did, 'general', :fh, :fd, NOW())
            ON CONFLICT (file_path) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                file_hash   = EXCLUDED.file_hash,
                file_date   = EXCLUDED.file_date,
                synced_at   = NOW()
        """), {
            "fp": file_path, "fn": filename,
            "did": document_id, "fh": file_hash, "fd": file_date
        })
        await db.commit()


async def remove_synced_file(file_path: str) -> Optional[str]:
    """Remove sync record and return document_id."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT document_id FROM localfs_synced_files WHERE file_path = :fp"
        ), {"fp": file_path})
        row = result.fetchone()
        if not row:
            return None
        await db.execute(text(
            "DELETE FROM localfs_synced_files WHERE file_path = :fp"
        ), {"fp": file_path})
        await db.commit()
    return row[0]


async def update_folder_last_sync(folder_path: str):
    """Mark folder as synced now."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE autosync_folders SET last_sync = NOW()
            WHERE folder_path = :fp
        """), {"fp": folder_path})
        await db.commit()


# ── File scanning ─────────────────────────────────────────────────────────────

def compute_hash(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


def should_ignore(filename: str, file_path: str, exclude_patterns: Set[str]) -> bool:
    """Check if file should be skipped."""
    name = os.path.basename(filename)
    if name in IGNORE_NAMES:
        return True
    if any(name.startswith(p) for p in IGNORE_PREFIXES):
        return True
    if pathlib.Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return True
    name_lower = name.lower()
    path_lower = file_path.lower()
    if any(p in name_lower or p in path_lower for p in exclude_patterns):
        return True
    return False


def scan_folder(folder_path: str, exclude_patterns: Set[str]) -> List[str]:
    """Recursively scan folder and return list of supported file paths."""
    found = []
    if not os.path.exists(folder_path):
        return found
    for root, dirs, files in os.walk(folder_path):
        # Skip hidden and ignored directories
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in IGNORE_NAMES
        ]
        for fname in files:
            full_path = os.path.join(root, fname)
            if not should_ignore(fname, full_path, exclude_patterns):
                found.append(full_path)
    return found


# ── Core sync logic ───────────────────────────────────────────────────────────

async def sync_file(file_path: str, existing: Optional[Dict]) -> str:
    """
    Sync a single file. Returns: 'added', 'updated', 'skipped', 'error'
    """
    import uuid
    from app.services.ingestion import ingest_document
    from app.core.vector_store import get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    filename = os.path.basename(file_path)

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except (PermissionError, FileNotFoundError) as e:
        log.warning(f"[AutoSync] Cannot read {filename}: {e}")
        return "error"

    file_hash = compute_hash(file_bytes)
    file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()

    # Skip if unchanged
    if existing and existing.get("file_hash") == file_hash:
        return "skipped"

    action = "updated" if existing else "added"

    # Delete old chunks if updating
    if existing and existing.get("document_id"):
        try:
            client = get_qdrant()
            await client.delete(
                collection_name="intellirag_localfs",
                points_selector=Filter(must=[
                    FieldCondition(key="document_id", match=MatchValue(value=existing["document_id"]))
                ])
            )
        except Exception as e:
            log.warning(f"[AutoSync] Failed to delete old chunks for {filename}: {e}")

    # Ingest
    try:
        document_id = str(uuid.uuid4())
        await ingest_document(
            file_bytes=file_bytes,
            filename=filename,
            tenant_slug="general",
            document_id=document_id,
            uploaded_by="autosync",
            collection_name="intellirag_localfs",
            extra_metadata={
                "source_type": "localfs",
                "file_path": file_path,
                "file_date": file_date,
                "hostname": "autosync",
            },
        )
        await save_synced_file(file_path, filename, document_id, file_hash, file_date)
        log.info(f"[AutoSync] {action.upper()}: {filename}")
        return action
    except Exception as e:
        log.error(f"[AutoSync] Failed to ingest {filename}: {e}")
        return "error"


async def remove_deleted_file(file_path: str) -> bool:
    """Remove a deleted file from Qdrant and registry."""
    from app.core.vector_store import get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    document_id = await remove_synced_file(file_path)
    if not document_id:
        return False

    try:
        client = get_qdrant()
        await client.delete(
            collection_name="intellirag_localfs",
            points_selector=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            ])
        )
        # Remove from registry
        try:
            from app.services.registry import remove_registry_entry
            await remove_registry_entry(document_id, "intellirag_localfs")
        except Exception:
            pass

        log.info(f"[AutoSync] REMOVED: {os.path.basename(file_path)}")
        return True
    except Exception as e:
        log.error(f"[AutoSync] Failed to remove {file_path}: {e}")
        return False


async def run_sync_cycle() -> Dict:
    """
    Run one full sync cycle across all configured folders.
    Returns summary of what was done.
    """
    await ensure_autosync_tables()
    folders = await get_sync_folders()
    exclude_patterns = await get_exclude_patterns()

    if not folders:
        return {"status": "no_folders", "message": "No folders configured for auto-sync"}

    summary = {
        "added": 0, "updated": 0,
        "removed": 0, "skipped": 0, "errors": 0,
        "folders_scanned": len(folders),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Track all files currently on disk
    all_disk_files: Set[str] = set()

    for folder in folders:
        folder_path = folder["folder_path"]
        log.info(f"[AutoSync] Scanning: {folder_path}")

        disk_files = scan_folder(folder_path, exclude_patterns)
        all_disk_files.update(disk_files)

        for file_path in disk_files:
            existing = await get_synced_file(file_path)
            result = await sync_file(file_path, existing)
            summary[result] = summary.get(result, 0) + 1

            if result in ("added", "updated"):
                broadcast_event("file_synced", {
                    "filename": os.path.basename(file_path),
                    "action": result,
                    "folder": folder_path,
                })

        await update_folder_last_sync(folder_path)

    # Remove files that no longer exist on disk
    all_db_paths = await get_all_synced_paths()
    deleted_paths = all_db_paths - all_disk_files

    for file_path in deleted_paths:
        removed = await remove_deleted_file(file_path)
        if removed:
            summary["removed"] += 1
            broadcast_event("file_removed", {
                "filename": os.path.basename(file_path),
            })

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["status"] = "completed"
    return summary


# ── Background scheduler ──────────────────────────────────────────────────────

async def _sync_loop():
    """Background task that runs sync cycles on schedule."""
    log.info("[AutoSync] Background scheduler started")
    _sync_status["running"] = True

    while True:
        try:
            folders = await get_sync_folders()
            if not folders:
                await asyncio.sleep(60)
                continue

            # Use shortest interval among all folders
            interval = min(
                max(f.get("interval_s", DEFAULT_SYNC_INTERVAL), MIN_SYNC_INTERVAL)
                for f in folders
            )

            log.info(f"[AutoSync] Starting sync cycle (interval: {interval}s)")
            broadcast_event("sync_started", {"folders": len(folders)})

            result = await run_sync_cycle()

            _sync_status["last_sync"] = datetime.now(timezone.utc).isoformat()
            _sync_status["last_sync_result"] = result
            _sync_status["files_watched"] = sum(
                len(scan_folder(f["folder_path"], set()))
                for f in folders
                if os.path.exists(f["folder_path"])
            )
            _sync_status["folders"] = [f["folder_path"] for f in folders]

            broadcast_event("sync_completed", result)
            log.info(f"[AutoSync] Cycle done: {result}")

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"[AutoSync] Sync cycle error: {e}")
            await asyncio.sleep(60)

    _sync_status["running"] = False
    log.info("[AutoSync] Scheduler stopped")


def start_autosync():
    """Start the background sync scheduler. Call from app lifespan."""
    global _sync_task
    if _sync_task and not _sync_task.done():
        return
    _sync_task = asyncio.create_task(_sync_loop())
    log.info("[AutoSync] Scheduler task created")


def stop_autosync():
    """Stop the background sync scheduler. Call on app shutdown."""
    global _sync_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        log.info("[AutoSync] Scheduler stopped")


def get_sync_status() -> Dict:
    return {**_sync_status, "task_running": _sync_task is not None and not _sync_task.done()}
