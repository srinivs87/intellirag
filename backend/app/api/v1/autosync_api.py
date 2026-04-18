"""
Auto-Sync API — manage folder watching, trigger manual syncs, stream events.

Endpoints:
  GET  /api/autosync/status          — current sync status
  GET  /api/autosync/folders         — list configured folders
  POST /api/autosync/folders         — add folder to watch
  DELETE /api/autosync/folders/{id}  — remove folder
  POST /api/autosync/run-now         — trigger immediate sync
  GET  /api/autosync/stream          — SSE stream for real-time events
"""
import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.autosync_service import (
    ensure_autosync_tables,
    get_sync_folders,
    get_sync_status,
    run_sync_cycle,
    add_subscriber,
    remove_subscriber,
    scan_folder,
)

log = logging.getLogger("intellirag.autosync_api")
router = APIRouter()


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/autosync/status")
async def autosync_status():
    """Get current auto-sync status and statistics."""
    await ensure_autosync_tables()
    status = get_sync_status()
    folders = await get_sync_folders()

    # Count total files being watched
    total_files = 0
    for folder in folders:
        path = folder["folder_path"]
        if os.path.exists(path):
            try:
                files = scan_folder(path, set())
                total_files += len(files)
            except Exception:
                pass

    return {
        "scheduler_running": status["task_running"],
        "last_sync": status.get("last_sync"),
        "last_sync_result": status.get("last_sync_result"),
        "folders_count": len(folders),
        "files_watched": total_files,
        "folders": [
            {
                "id": f["id"],
                "path": f["folder_path"],
                "enabled": f["enabled"],
                "interval_s": f["interval_s"],
                "last_sync": str(f["last_sync"]) if f["last_sync"] else None,
            }
            for f in folders
        ],
    }


# ── Folder management ─────────────────────────────────────────────────────────

class AddFolderRequest(BaseModel):
    folder_path: str
    interval_s: Optional[int] = 300  # default 5 min


@router.get("/api/autosync/folders")
async def list_folders():
    """List all configured auto-sync folders."""
    await ensure_autosync_tables()
    folders = await get_sync_folders()
    return {"folders": folders, "total": len(folders)}


@router.post("/api/autosync/folders")
async def add_folder(req: AddFolderRequest):
    """Add a folder to the auto-sync watch list."""
    await ensure_autosync_tables()

    folder_path = os.path.expanduser(req.folder_path)

    if not os.path.exists(folder_path):
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}. "
                   f"Please ensure the path exists on the server."
        )

    if not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {folder_path}"
        )

    interval = max(req.interval_s or 300, 60)

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO autosync_folders (folder_path, interval_s)
                VALUES (:path, :interval)
                ON CONFLICT (folder_path) DO UPDATE SET
                    enabled    = TRUE,
                    interval_s = EXCLUDED.interval_s
            """), {"path": folder_path, "interval": interval})
            await db.commit()

        # Count files in folder
        files = scan_folder(folder_path, set())
        log.info(f"[AutoSync] Added folder: {folder_path} ({len(files)} files)")

        return {
            "status": "ok",
            "folder_path": folder_path,
            "interval_s": interval,
            "files_found": len(files),
            "message": f"Folder added. Found {len(files)} files to sync."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/autosync/folders/{folder_id}")
async def remove_folder(folder_id: str):
    """Remove a folder from the auto-sync watch list."""
    await ensure_autosync_tables()
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT folder_path FROM autosync_folders WHERE id = :id"
        ), {"id": folder_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder not found")

        await db.execute(text(
            "DELETE FROM autosync_folders WHERE id = :id"
        ), {"id": folder_id})
        await db.commit()

    return {"status": "ok", "removed": row[0]}


@router.patch("/api/autosync/folders/{folder_id}")
async def toggle_folder(folder_id: str, enabled: bool):
    """Enable or disable a sync folder without removing it."""
    await ensure_autosync_tables()
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE autosync_folders SET enabled = :enabled WHERE id = :id
        """), {"enabled": enabled, "id": folder_id})
        await db.commit()
    return {"status": "ok", "enabled": enabled}


# ── Manual sync trigger ───────────────────────────────────────────────────────

@router.post("/api/autosync/run-now")
async def trigger_sync():
    """Trigger an immediate sync cycle without waiting for the schedule."""
    await ensure_autosync_tables()
    folders = await get_sync_folders()

    if not folders:
        raise HTTPException(
            status_code=400,
            detail="No folders configured. Add a folder first."
        )

    try:
        result = await run_sync_cycle()
        return {"status": "ok", "result": result}
    except Exception as e:
        log.error(f"[AutoSync] Manual sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Preview folder contents ───────────────────────────────────────────────────

@router.get("/api/autosync/preview")
async def preview_folder(path: str):
    """Preview files that would be synced from a folder path."""
    folder_path = os.path.expanduser(path)

    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail=f"Path not found: {folder_path}")

    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    try:
        files = scan_folder(folder_path, set())
        return {
            "folder_path": folder_path,
            "files": [
                {
                    "name": os.path.basename(f),
                    "path": f,
                    "size_kb": round(os.path.getsize(f) / 1024, 1),
                    "ext": os.path.splitext(f)[1].lower(),
                }
                for f in sorted(files)[:50]  # Max 50 preview
            ],
            "total": len(files),
            "showing": min(len(files), 50),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SSE stream for real-time sync events ─────────────────────────────────────

@router.get("/api/autosync/stream")
async def sync_event_stream():
    """
    Server-Sent Events stream for real-time sync notifications.
    UI connects to this to get live updates when files are synced.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    add_subscriber(queue)

    async def generate():
        try:
            # Send initial status
            status = get_sync_status()
            yield f"data: {json.dumps({'type': 'connected', 'status': status})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            remove_subscriber(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
