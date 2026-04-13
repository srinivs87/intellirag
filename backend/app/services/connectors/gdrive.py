"""
Google Drive Connector
- Authenticates using a service account JSON key
- Lists all files from My Drive (or a specific folder)
- Downloads and ingests into IntelliRAG via the existing pipeline
- Tracks sync state in PostgreSQL to avoid re-ingesting unchanged files
- Supports: PDF, DOCX, TXT, MD, Google Docs, Google Sheets, PPTX
"""

import io
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.ingestion import ingest_document

# File types we can handle
SUPPORTED_MIME_TYPES = {
    "application/pdf":                                                    ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":  ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain":                                                          ".txt",
    "text/markdown":                                                       ".md",
    # Google native types → export as Office format
    "application/vnd.google-apps.document":     ".docx",
    "application/vnd.google-apps.spreadsheet":  ".xlsx",
    "application/vnd.google-apps.presentation": ".pptx",
}

# Google Docs → export MIME types
EXPORT_MIME = {
    "application/vnd.google-apps.document":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation":
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_drive_service(credentials_json: dict):
    """Build Google Drive API service from service account credentials dict."""
    creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


_sync_progress: dict = {}

def get_sync_progress(connector_id: str) -> dict:
    return _sync_progress.get(connector_id, {})

def clear_sync_progress(connector_id: str):
    _sync_progress.pop(connector_id, None)

# DB-based progress (works across processes)
async def update_progress_db(connector_id: str, total: int, synced: int, skipped: int, failed: int):
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                UPDATE gdrive_connectors 
                SET files_synced = :synced
                WHERE id = :id
            """), {"synced": synced + skipped, "id": connector_id})
            await db.commit()
    except Exception:
        pass


async def ensure_sync_tables():
    """Create connector sync tracking tables if they don't exist."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS gdrive_connectors (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_slug  VARCHAR(50) NOT NULL,
                name         VARCHAR(100) NOT NULL,
                folder_id    VARCHAR(200),
                credentials  TEXT NOT NULL,
                status       VARCHAR(20) DEFAULT 'idle',
                last_sync_at TIMESTAMPTZ,
                files_synced INT DEFAULT 0,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS gdrive_synced_files (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                connector_id  UUID REFERENCES gdrive_connectors(id) ON DELETE CASCADE,
                file_id       VARCHAR(200) NOT NULL,
                filename      VARCHAR(500),
                modified_at   TIMESTAMPTZ,
                document_id   VARCHAR(200),
                synced_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(connector_id, file_id)
            )
        """))
        await db.commit()


async def save_connector(
    tenant_slug: str,
    name: str,
    credentials_json: dict,
    folder_id: Optional[str] = None,
) -> str:
    """Save a connector configuration to the database."""
    await ensure_sync_tables()
    connector_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO gdrive_connectors (id, tenant_slug, name, folder_id, credentials, status)
            VALUES (:id, :tenant, :name, :folder_id, :creds, 'idle')
        """), {
            "id": connector_id,
            "tenant": tenant_slug,
            "name": name,
            "folder_id": folder_id,
            "creds": json.dumps(credentials_json),
        })
        await db.commit()
    return connector_id


async def list_connectors(tenant_slug: str) -> List[Dict]:
    """List all connectors for a tenant."""
    await ensure_sync_tables()
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT id, name, folder_id, status, last_sync_at, files_synced, created_at
            FROM gdrive_connectors WHERE tenant_slug = :t ORDER BY created_at DESC
        """), {"t": tenant_slug})
        rows = r.fetchall()
        return [{
            "id": str(row.id),
            "name": row.name,
            "folder_id": row.folder_id,
            "status": row.status,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "files_synced": row.files_synced,
        } for row in rows]


async def get_connector(connector_id: str) -> Optional[Dict]:
    """Fetch a single connector including credentials."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT * FROM gdrive_connectors WHERE id = :id
        """), {"id": connector_id})
        row = r.fetchone()
        if not row:
            return None
        return {
            "id": str(row.id),
            "tenant_slug": row.tenant_slug,
            "name": row.name,
            "folder_id": row.folder_id,
            "credentials": json.loads(row.credentials),
            "status": row.status,
            "last_sync_at": row.last_sync_at,
            "files_synced": row.files_synced,
        }


async def delete_connector(connector_id: str):
    """Delete a connector and all its sync history."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM gdrive_connectors WHERE id = :id"),
            {"id": connector_id}
        )
        await db.commit()


def _list_all_files(service, folder_id: Optional[str] = None) -> List[Dict]:
    """
    List all supported files from Drive.
    If folder_id is given, only files inside that folder (recursive).
    Otherwise lists all files in My Drive.
    """
    all_files = []
    mime_filter = " or ".join([f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES])
    page_token = None

    if folder_id:
        query = f"('{folder_id}' in parents) and ({mime_filter}) and trashed=false"
    else:
        query = f"({mime_filter}) and trashed=false and 'me' in owners"

    while True:
        response = service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            pageToken=page_token,
            pageSize=100,
        ).execute()

        all_files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return all_files


def _download_file(service, file_id: str, mime_type: str) -> bytes:
    """Download a file — export Google native formats to Office formats."""
    buffer = io.BytesIO()

    if mime_type in EXPORT_MIME:
        # Google Docs/Sheets/Slides → export as Office format
        request = service.files().export_media(
            fileId=file_id,
            mimeType=EXPORT_MIME[mime_type]
        )
    else:
        request = service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()


async def _get_synced_file(connector_id: str, file_id: str) -> Optional[Dict]:
    """Check if a file has already been synced and get its metadata."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT file_id, modified_at, document_id FROM gdrive_synced_files
            WHERE connector_id = :cid AND file_id = :fid
        """), {"cid": connector_id, "fid": file_id})
        row = r.fetchone()
        if not row:
            return None
        return {"file_id": row.file_id, "modified_at": row.modified_at, "document_id": row.document_id}


async def _mark_file_synced(connector_id: str, file_id: str, filename: str, modified_at: str, document_id: str):
    """Record a file as successfully synced."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO gdrive_synced_files (connector_id, file_id, filename, modified_at, document_id, synced_at)
            VALUES (:cid, :fid, :fname, :mod_at, :doc_id, NOW())
            ON CONFLICT (connector_id, file_id) DO UPDATE
            SET filename=EXCLUDED.filename, modified_at=EXCLUDED.modified_at,
                document_id=EXCLUDED.document_id, synced_at=NOW()
        """), {
            "cid": connector_id, "fid": file_id, "fname": filename,
            "mod_at": datetime.fromisoformat(modified_at.replace("Z", "+00:00")) if modified_at else None, "doc_id": document_id,
        })
        await db.commit()


async def run_sync(connector_id: str) -> Dict[str, Any]:
    """
    Main sync function — call this to sync a connector.
    Skips files that haven't changed since last sync.
    Returns sync summary.
    """
    connector = await get_connector(connector_id)
    if not connector:
        return {"error": "Connector not found"}

    # Mark as syncing
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE gdrive_connectors SET status='syncing' WHERE id=:id"
        ), {"id": connector_id})
        await db.commit()

    results = {"synced": 0, "skipped": 0, "failed": 0, "errors": []}

    try:
        service = build_drive_service(connector["credentials"])
        files = _list_all_files(service, connector.get("folder_id"))

        print(f"[GDrive] Found {len(files)} files for connector {connector_id}")
        # Store progress after files are fetched
        _sync_progress[connector_id] = {"total": len(files), "synced": 0, "skipped": 0, "failed": 0, "status": "syncing"}

        for file in files:
            file_id    = file["id"]
            filename   = file["name"]
            mime_type  = file["mimeType"]
            modified_at = file.get("modifiedTime", "")

            try:
                # Check if already synced and unchanged
                existing = await _get_synced_file(connector_id, file_id)
                if existing and existing["modified_at"] and str(existing["modified_at"]) >= modified_at:
                    results["skipped"] += 1
                    if connector_id in _sync_progress:
                        _sync_progress[connector_id]["skipped"] = results["skipped"]
                    continue

                # Download file
                file_bytes = _download_file(service, file_id, mime_type)
                if not file_bytes:
                    results["failed"] += 1
                    results["errors"].append(f"{filename}: empty download")
                    continue

                # Get correct filename extension
                ext = SUPPORTED_MIME_TYPES.get(mime_type, "")
                if not filename.endswith(ext) and ext:
                    filename = filename + ext

                # Ingest into RAG pipeline
                document_id = str(uuid.uuid4())
                await ingest_document(
                    file_bytes=file_bytes,
                    filename=filename,
                    tenant_slug=connector["tenant_slug"],
                    document_id=document_id,
                    uploaded_by=f"gdrive_connector:{connector_id}",
                    collection_name="intellirag_gdrive",
                    extra_metadata={"file_date": modified_at, "gdrive_file_id": file_id},
                )

                await _mark_file_synced(connector_id, file_id, filename, modified_at, document_id)
                results["synced"] += 1
                if connector_id in _sync_progress:
                    _sync_progress[connector_id]["synced"] = results["synced"]
                    _sync_progress[connector_id]["skipped"] = results["skipped"]
                print(f"[GDrive] Synced: {filename}")

            except Exception as e:
                results["failed"] += 1
                if connector_id in _sync_progress:
                    _sync_progress[connector_id]["failed"] = results["failed"]
                results["errors"].append(f"{filename}: {str(e)[:100]}")
                print(f"[GDrive] Failed {filename}: {e}")

        # Update connector status
        async with AsyncSessionLocal() as db:
            # Count actual total files in Qdrant for this connector
            total = await db.execute(text("""
                SELECT COUNT(DISTINCT file_id) FROM gdrive_synced_files
                WHERE connector_id = :id
            """), {"id": connector_id})
            total_count = total.scalar() or (results["synced"] + results["skipped"])
            await db.execute(text("""
                UPDATE gdrive_connectors
                SET status='idle', last_sync_at=NOW(),
                    files_synced = :total
                WHERE id=:id
            """), {"total": total_count, "id": connector_id})
            await db.commit()
        clear_sync_progress(connector_id)

    except Exception as e:
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "UPDATE gdrive_connectors SET status='error' WHERE id=:id"
            ), {"id": connector_id})
            await db.commit()
        results["error"] = str(e)
        print(f"[GDrive] Sync failed: {e}")

    print(f"[GDrive] Sync complete: {results}")
    return results
