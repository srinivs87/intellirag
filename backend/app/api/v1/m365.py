"""
Microsoft 365 Connector API — Full CRUD
add, list, update credentials, sync, delete
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text

from app.services.connectors.m365 import (
    save_m365_connector, list_m365_connectors,
    run_m365_sync, delete_m365_connector,
    ensure_m365_tables, get_m365_connector
)
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

router = APIRouter()


class M365ConnectorRequest(BaseModel):
    name: str
    tenant_id: str
    client_id: str
    client_secret: str
    sources: Optional[List[str]] = ["teams", "onedrive", "sharepoint"]
    sync_now: bool = True


class M365ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    sources: Optional[List[str]] = None
    sync_now: bool = False


@router.post("/m365/")
async def add_m365_connector(req: M365ConnectorRequest, background_tasks: BackgroundTasks):
    try:
        connector_id = await save_m365_connector(
            name=req.name, tenant_id=req.tenant_id,
            client_id=req.client_id, client_secret=req.client_secret,
            sources=req.sources,
        )
        if req.sync_now:
            background_tasks.add_task(run_m365_sync, connector_id)
        return {"connector_id": connector_id, "status": "created", "sync_started": req.sync_now, "sources": req.sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/m365/")
async def get_m365_connectors():
    await ensure_m365_tables()
    return {"connectors": await list_m365_connectors()}


@router.put("/m365/{connector_id}")
async def update_m365_connector(connector_id: str, req: M365ConnectorUpdate, background_tasks: BackgroundTasks):
    """Update M365 credentials, sources, or name. Re-sync if requested."""
    connector = await get_m365_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    import json
    async with AsyncSessionLocal() as db:
        if req.name:
            await db.execute(text("UPDATE m365_connectors SET name=:v WHERE id=:id"), {"v": req.name, "id": connector_id})
        if req.tenant_id:
            await db.execute(text("UPDATE m365_connectors SET tenant_id=:v WHERE id=:id"), {"v": req.tenant_id, "id": connector_id})
        if req.client_id:
            await db.execute(text("UPDATE m365_connectors SET client_id=:v WHERE id=:id"), {"v": req.client_id, "id": connector_id})
        if req.client_secret:
            await db.execute(text("UPDATE m365_connectors SET client_secret=:v WHERE id=:id"), {"v": req.client_secret, "id": connector_id})
        if req.sources:
            await db.execute(text("UPDATE m365_connectors SET sources=:v WHERE id=:id"), {"v": json.dumps(req.sources), "id": connector_id})
        await db.commit()

    if req.sync_now:
        background_tasks.add_task(run_m365_sync, connector_id)

    return {"status": "updated", "connector_id": connector_id, "sync_started": req.sync_now}


@router.post("/m365/{connector_id}/sync")
async def trigger_m365_sync(connector_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_m365_sync, connector_id)
    return {"status": "sync_started", "connector_id": connector_id}


@router.delete("/m365/{connector_id}")
async def remove_m365_connector(connector_id: str):
    await delete_m365_connector(connector_id)
    return {"status": "deleted", "connector_id": connector_id}

@router.get("/m365/file-location/{document_id}")
async def get_file_location(document_id: str):
    """Look up the OneDrive/SharePoint/Teams location of a file by document_id."""
    async with AsyncSessionLocal() as db:
        # Try by document_id first
        r = await db.execute(text("""
            SELECT f.filename, f.file_id, f.source_type, f.web_url, f.file_path, f.synced_at,
                   c.name as connector_name
            FROM m365_synced_files f
            JOIN m365_connectors c ON f.connector_id = c.id
            WHERE f.document_id = :doc_id
            LIMIT 1
        """), {"doc_id": document_id})
        row = r.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="File location not found. Please use Sync now to update file links.")

        web_url = row.web_url
        # If no web_url stored, build a fallback OneDrive search URL
        if not web_url and row.file_id:
            web_url = f"https://onedrive.live.com/?id={row.file_id}"

        return {
            "document_id": document_id,
            "filename": row.filename,
            "source_type": row.source_type,
            "web_url": web_url,
            "file_path": row.file_path,
            "connector_name": row.connector_name,
            "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        }


@router.get("/m365/files/")
async def list_m365_files():
    """List all synced M365 files with their locations."""
    await ensure_m365_tables()
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT f.document_id, f.filename, f.source_type, f.web_url,
                   f.file_path, f.synced_at, c.name as connector_name
            FROM m365_synced_files f
            JOIN m365_connectors c ON f.connector_id = c.id
            ORDER BY f.synced_at DESC
        """))
        files = [{
            "document_id": row.document_id,
            "filename": row.filename,
            "source_type": row.source_type,
            "web_url": row.web_url,
            "file_path": row.file_path,
            "connector_name": row.connector_name,
            "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        } for row in r.fetchall()]
    return {"files": files, "total": len(files)}


@router.post("/m365/{connector_id}/populate-links")
async def populate_file_links(connector_id: str, background_tasks: BackgroundTasks):
    """Clear modified_at for files missing web_url so the next sync re-fetches their webUrl."""
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                UPDATE m365_synced_files
                SET modified_at = NULL
                WHERE connector_id = :cid AND (web_url IS NULL OR web_url = '')
            """), {"cid": connector_id})
            await db.commit()
            count = r.rowcount
        # Now trigger a real sync so those files get re-processed with webUrl capture
        background_tasks.add_task(run_m365_sync, connector_id)
        return {"status": "started", "count": count, "message": f"Cleared {count} file timestamps. Re-syncing to fetch real file links..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _populate_links_task(connector_id: str):
    """Build web_url for all synced files from file_path and source_type."""
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT file_id, filename, file_path, source_type
                FROM m365_synced_files
                WHERE connector_id = :cid AND (web_url IS NULL OR web_url = '')
            """), {"cid": connector_id})
            rows = r.fetchall()
            print(f"[M365] Building URLs for {len(rows)} files...")
            updated = 0
            for row in rows:
                web_url = ""
                file_path = (row.file_path or "").strip()
                source_type = (row.source_type or "").lower()

                if file_path:
                    if not file_path.startswith("/"):
                        file_path = "/" + file_path
                    if source_type == "onedrive":
                        # OneDrive personal files
                        web_url = f"https://altencalsoftlabs-my.sharepoint.com/personal{file_path}"
                    else:
                        # SharePoint / Teams files
                        web_url = f"https://altencalsoftlabs.sharepoint.com{file_path}"
                else:
                    # No path stored — use OneDrive search
                    if source_type == "onedrive":
                        web_url = f"https://altencalsoftlabs-my.sharepoint.com/_layouts/15/onedrive.aspx?search={row.filename.replace(' ', '+')}"
                    else:
                        web_url = f"https://altencalsoftlabs.sharepoint.com/_layouts/15/search.aspx/siteall?q={row.filename.replace(' ', '+')}"

                await db.execute(text("""
                    UPDATE m365_synced_files SET web_url = :url
                    WHERE connector_id = :cid AND file_id = :fid
                """), {"url": web_url, "cid": connector_id, "fid": row.file_id})
                updated += 1
            await db.commit()
            print(f"[M365] Built URLs for {updated} files.")
    except Exception as e:
        print(f"[M365] populate-links error: {e}")


