"""
Connector API — Google Drive
Full CRUD: add, list, update credentials/folder, sync, delete
"""
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text

from app.services.connectors.gdrive import (
    save_connector, list_connectors, run_sync,
    delete_connector, ensure_sync_tables, get_connector
)
from app.core.database import AsyncSessionLocal

router = APIRouter()


@router.post("/gdrive/")
async def add_gdrive_connector(
    background_tasks: BackgroundTasks,
    tenant: str = Form(default="gdrive"),
    name: str = Form(...),
    credentials_file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    sync_now: bool = Form(True),
):
    try:
        content = await credentials_file.read()
        credentials_json = json.loads(content)
        if credentials_json.get("type") != "service_account":
            raise HTTPException(status_code=400, detail="File must be a service account JSON key")

        connector_id = await save_connector(
            tenant_slug="gdrive",
            name=name,
            credentials_json=credentials_json,
            folder_id=folder_id or None,
        )
        if sync_now:
            background_tasks.add_task(run_sync, connector_id)

        return {"connector_id": connector_id, "status": "created", "sync_started": sync_now}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gdrive/")
async def get_all_gdrive_connectors():
    """List all Google Drive connectors across all tenants."""
    await ensure_sync_tables()
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT id, tenant_slug, name, folder_id, status, last_sync_at, files_synced, created_at
            FROM gdrive_connectors ORDER BY created_at DESC
        """))
        rows = r.fetchall()
        connectors = [{
            "id": str(row.id), "name": row.name, "tenant_slug": row.tenant_slug,
            "folder_id": row.folder_id, "status": row.status,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "files_synced": row.files_synced or 0,
        } for row in rows]
    return {"connectors": connectors}


@router.get("/gdrive/{tenant_slug}")
async def get_connectors(tenant_slug: str):
    await ensure_sync_tables()
    return {"tenant": tenant_slug, "connectors": await list_connectors(tenant_slug)}


@router.put("/gdrive/{connector_id}")
async def update_gdrive_connector(
    connector_id: str,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    credentials_file: Optional[UploadFile] = File(None),
    folder_id: Optional[str] = Form(None),
    sync_now: bool = Form(False),
):
    """Update connector name, credentials, or folder. Re-sync if requested."""
    connector = await get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    updates = {}
    if name:
        updates["name"] = name
    if folder_id is not None:
        updates["folder_id"] = folder_id or None
    if credentials_file:
        content = await credentials_file.read()
        try:
            creds = json.loads(content)
            if creds.get("type") != "service_account":
                raise HTTPException(status_code=400, detail="Invalid service account JSON")
            updates["credentials"] = json.dumps(creds)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")

    if updates:
        async with AsyncSessionLocal() as db:
            for key, val in updates.items():
                await db.execute(
                    text(f"UPDATE gdrive_connectors SET {key} = :{key} WHERE id = :id"),
                    {key: val, "id": connector_id}
                )
            await db.commit()

    if sync_now:
        background_tasks.add_task(run_sync, connector_id)

    return {"status": "updated", "connector_id": connector_id, "sync_started": sync_now}


@router.post("/gdrive/{connector_id}/sync")
async def trigger_sync(connector_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_sync, connector_id)
    return {"status": "sync_started", "connector_id": connector_id}



@router.get("/gdrive/{connector_id}/progress")
async def get_gdrive_sync_progress(connector_id: str):
    """Returns live sync progress purely from DB - no in-memory state needed."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # Get connector status
        conn_result = await db.execute(text(
            "SELECT status, files_synced FROM gdrive_connectors WHERE id = :id"
        ), {"id": connector_id})
        conn_row = conn_result.fetchone()
        if not conn_row:
            return {"total": 0, "synced": 0, "skipped": 0, "status": "idle", "percent": 0}

        # Count how many files have been synced so far in this session
        count_result = await db.execute(text(
            "SELECT COUNT(*) FROM gdrive_synced_files WHERE connector_id = :id"
        ), {"id": connector_id})
        synced_count = count_result.scalar() or 0

    status = conn_row.status
    
    # We use synced_count as progress indicator
    # For percent: assume ~76 files (known total), update when done
    ESTIMATED_TOTAL = 80  # slightly over to avoid hitting 100% prematurely
    
    if status == "idle":
        final_count = conn_row.files_synced or synced_count
        return {"total": final_count, "synced": final_count, "skipped": 0, "status": "idle", "percent": 100}
    
    percent = min(round(synced_count / ESTIMATED_TOTAL * 100), 95) if synced_count > 0 else 5
    
    return {
        "total": ESTIMATED_TOTAL,
        "synced": synced_count,
        "skipped": 0,
        "status": status,
        "percent": percent
    }


@router.delete("/gdrive/{connector_id}")
async def remove_connector(connector_id: str):
    await delete_connector(connector_id)
    return {"status": "deleted", "connector_id": connector_id}


@router.get("/gdrive/file-location/{document_id}")
async def get_gdrive_file_location(document_id: str):
    """Look up the Google Drive web URL for a file by document_id."""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT f.filename, f.document_id,
                   'https://drive.google.com/open?id=' || f.file_id as web_url
            FROM gdrive_synced_files f
            WHERE f.document_id = :doc_id
            LIMIT 1
        """), {"doc_id": document_id})
        row = r.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="File not found")
        return {
            "document_id": document_id,
            "filename": row.filename,
            "web_url": row.web_url,
        }
