"""
Microsoft 365 Connector
- Authenticates via Azure AD app credentials (client credentials flow)
- Reads files from: Teams channel Files tabs, OneDrive, SharePoint document libraries
- Downloads and ingests into separate Qdrant collections per source type
- Tracks sync state in PostgreSQL to skip unchanged files
- Supports: PDF, DOCX, XLSX, PPTX, TXT, MD
"""

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.ingestion import ingest_document

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md"}

# Source type → Qdrant collection name
SOURCE_COLLECTIONS = {
    "teams":       "intellirag_teams",
    "onedrive":    "intellirag_onedrive",
    "sharepoint":  "intellirag_sharepoint",
}


async def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get OAuth2 access token using client credentials flow."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        })
        response.raise_for_status()
        return response.json()["access_token"]


async def graph_get(token: str, path: str, params: dict = None) -> dict:
    """Make a GET request to Microsoft Graph API."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        response.raise_for_status()
        return response.json()


async def download_file(token: str, download_url: str) -> bytes:
    """Download file content from Graph API."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.content


async def ensure_m365_tables():
    """Create M365 connector tracking tables."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS m365_connectors (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name          VARCHAR(100) NOT NULL,
                tenant_id     VARCHAR(200) NOT NULL,
                client_id     VARCHAR(200) NOT NULL,
                client_secret TEXT NOT NULL,
                sources       JSONB DEFAULT '["teams","onedrive","sharepoint"]',
                status        VARCHAR(20) DEFAULT 'idle',
                last_sync_at  TIMESTAMPTZ,
                files_synced  INT DEFAULT 0,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS m365_synced_files (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                connector_id  UUID REFERENCES m365_connectors(id) ON DELETE CASCADE,
                file_id       VARCHAR(500) NOT NULL,
                filename      VARCHAR(500),
                source_type   VARCHAR(20),
                modified_at   TIMESTAMPTZ,
                document_id   VARCHAR(200),
                web_url       TEXT,
                file_path     TEXT,
                synced_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(connector_id, file_id)
            )
        """))
        # Add columns if upgrading from older schema
        try:
            await db.execute(text("ALTER TABLE m365_synced_files ADD COLUMN IF NOT EXISTS web_url TEXT"))
            await db.execute(text("ALTER TABLE m365_synced_files ADD COLUMN IF NOT EXISTS file_path TEXT"))
        except Exception:
            pass
        await db.commit()


async def save_m365_connector(
    name: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    sources: List[str] = None,
) -> str:
    await ensure_m365_tables()
    connector_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO m365_connectors (id, name, tenant_id, client_id, client_secret, sources)
            VALUES (:id, :name, :tid, :cid, :secret, :sources)
        """), {
            "id": connector_id, "name": name,
            "tid": tenant_id, "cid": client_id,
            "secret": client_secret,
            "sources": json.dumps(sources or ["teams", "onedrive", "sharepoint"]),
        })
        await db.commit()
    return connector_id


async def list_m365_connectors() -> List[Dict]:
    await ensure_m365_tables()
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT id, name, sources, status, last_sync_at, files_synced, created_at
            FROM m365_connectors ORDER BY created_at DESC
        """))
        return [{
            "id": str(row.id), "name": row.name,
            "sources": row.sources if isinstance(row.sources, list) else json.loads(row.sources or "[]"),
            "status": row.status,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "files_synced": row.files_synced,
        } for row in r.fetchall()]


async def get_m365_connector(connector_id: str) -> Optional[Dict]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT * FROM m365_connectors WHERE id = :id"),
            {"id": connector_id}
        )
        row = r.fetchone()
        if not row:
            return None
        return {
            "id": str(row.id), "name": row.name,
            "tenant_id": row.tenant_id, "client_id": row.client_id,
            "client_secret": row.client_secret,
            "sources": row.sources if isinstance(row.sources, list) else json.loads(row.sources or "[]"),
            "status": row.status, "files_synced": row.files_synced,
        }


async def delete_m365_connector(connector_id: str):
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM m365_connectors WHERE id = :id"), {"id": connector_id})
        await db.commit()


def _is_supported(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)


async def _already_synced(connector_id: str, file_id: str, modified_at: str) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT modified_at FROM m365_synced_files
            WHERE connector_id = :cid AND file_id = :fid
        """), {"cid": connector_id, "fid": file_id})
        row = r.fetchone()
        if not row or not row.modified_at:
            return False
        stored = row.modified_at.replace(tzinfo=timezone.utc) if row.modified_at.tzinfo is None else row.modified_at
        incoming = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
        return stored >= incoming


async def _mark_synced(connector_id: str, file_id: str, filename: str,
                       source_type: str, modified_at: str, document_id: str,
                       web_url: str = None, file_path: str = None):
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO m365_synced_files
                (connector_id, file_id, filename, source_type, modified_at, document_id, web_url, file_path, synced_at)
            VALUES (:cid, :fid, :fname, :stype, :mod_at, :doc_id, :web_url, :file_path, NOW())
            ON CONFLICT (connector_id, file_id) DO UPDATE
            SET filename=EXCLUDED.filename, modified_at=EXCLUDED.modified_at,
                document_id=EXCLUDED.document_id, web_url=EXCLUDED.web_url,
                file_path=EXCLUDED.file_path, synced_at=NOW()
        """), {
            "cid": connector_id, "fid": file_id, "fname": filename,
            "stype": source_type,
            "mod_at": datetime.fromisoformat(modified_at.replace("Z", "+00:00")) if modified_at else None,
            "doc_id": document_id,
            "web_url": web_url,
            "file_path": file_path,
        })
        await db.commit()


async def _ingest_file(token: str, item: dict, source_type: str,
                       connector_id: str, results: dict):
    """Download and ingest a single file item."""
    file_id = item["id"]
    filename = item["name"]
    modified_at = item.get("lastModifiedDateTime", "")

    if not _is_supported(filename):
        results["skipped"] += 1
        return

    if await _already_synced(connector_id, file_id, modified_at):
        # Still update web_url if we have it and it was missing before
        web_url_check = item.get("webUrl", "")
        if web_url_check:
            async with __import__("app.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
                from sqlalchemy import text as _text
                await db.execute(_text("""
                    UPDATE m365_synced_files
                    SET web_url = :url
                    WHERE connector_id = :cid AND file_id = :fid AND (web_url IS NULL OR web_url = '')
                """), {"url": web_url_check, "cid": connector_id, "fid": file_id})
                await db.commit()
        results["skipped"] += 1
        return

    try:
        download_url = item.get("@microsoft.graph.downloadUrl") or \
                       f"{GRAPH_BASE}/drives/{item['parentReference']['driveId']}/items/{file_id}/content"
        file_bytes = await download_file(token, download_url)
        if not file_bytes:
            results["failed"] += 1
            return

        # Extract location metadata from Graph API response
        web_url = item.get("webUrl", "")
        parent_path = item.get("parentReference", {}).get("path", "")
        # Clean up the path - remove /drives/.../root: prefix
        if "root:" in parent_path:
            parent_path = parent_path.split("root:")[-1]
        file_path = f"{parent_path}/{filename}" if parent_path else filename

        collection_name = SOURCE_COLLECTIONS[source_type]
        document_id = str(uuid.uuid4())

        await ingest_document(
            file_bytes=file_bytes,
            filename=filename,
            tenant_slug=collection_name.replace("intellirag_", ""),
            document_id=document_id,
            uploaded_by=f"m365_connector:{connector_id}:{source_type}",
            extra_metadata={"web_url": web_url, "file_path": file_path, "source_type": source_type},
        )

        await _mark_synced(connector_id, file_id, filename, source_type, modified_at, document_id, web_url, file_path)
        results["synced"] += 1
        print(f"[M365/{source_type}] Synced: {filename} — {file_path}")

    except Exception as e:
        results["failed"] += 1
        results["errors"].append(f"{filename}: {str(e)[:100]}")
        print(f"[M365/{source_type}] Failed {filename}: {e}")


async def sync_onedrive(token: str, connector_id: str, results: dict):
    """Sync OneDrive files — uses /users endpoint for app-level auth."""
    print("[M365] Syncing OneDrive...")
    try:
        # Get all users, then their drives (works with application permissions)
        users_data = await graph_get(token, "/users", {"$select": "id,displayName", "$top": "100"})
        for user in users_data.get("value", []):
            user_id = user["id"]
            user_name = user.get("displayName", user_id)
            try:
                drive_data = await graph_get(token, f"/users/{user_id}/drive/root/children")
                for item in drive_data.get("value", []):
                    if item.get("folder"):
                        try:
                            drive_id = item.get("parentReference", {}).get("driveId", "")
                            folder_data = await graph_get(token, f"/drives/{drive_id}/items/{item['id']}/children")
                            for f_item in folder_data.get("value", []):
                                if not f_item.get("folder"):
                                    await _ingest_file(token, f_item, "onedrive", connector_id, results)
                        except Exception as e:
                            print(f"[M365/OneDrive] Folder error for {user_name}: {e}")
                    else:
                        await _ingest_file(token, item, "onedrive", connector_id, results)
            except Exception as e:
                print(f"[M365/OneDrive] User {user_name}: {e}")
    except Exception as e:
        print(f"[M365/OneDrive] Error: {e}")
        results["errors"].append(f"OneDrive: {str(e)[:100]}")


async def sync_sharepoint(token: str, connector_id: str, results: dict):
    """Sync files from all accessible SharePoint sites."""
    print("[M365] Syncing SharePoint...")
    try:
        sites_data = await graph_get(token, "/sites", {"search": "*"})
        for site in sites_data.get("value", []):
            site_id = site["id"]
            site_name = site.get("displayName", site_id)
            try:
                drives_data = await graph_get(token, f"/sites/{site_id}/drives")
                for drive in drives_data.get("value", []):
                    drive_id = drive["id"]
                    try:
                        items_data = await graph_get(token, f"/drives/{drive_id}/root/children")
                        for item in items_data.get("value", []):
                            if not item.get("folder"):
                                await _ingest_file(token, item, "sharepoint", connector_id, results)
                    except Exception as e:
                        print(f"[M365/SharePoint] Drive error in {site_name}: {e}")
            except Exception as e:
                print(f"[M365/SharePoint] Site error {site_name}: {e}")
    except Exception as e:
        print(f"[M365/SharePoint] Error: {e}")
        results["errors"].append(f"SharePoint: {str(e)[:100]}")


async def sync_teams(token: str, connector_id: str, results: dict):
    """Sync files from all joined Teams channels."""
    print("[M365] Syncing Teams...")
    try:
        teams_data = await graph_get(token, "/me/joinedTeams")
        for team in teams_data.get("value", []):
            team_id = team["id"]
            team_name = team.get("displayName", team_id)
            try:
                channels_data = await graph_get(token, f"/teams/{team_id}/channels")
                for channel in channels_data.get("value", []):
                    channel_id = channel["id"]
                    try:
                        files_data = await graph_get(
                            token,
                            f"/teams/{team_id}/channels/{channel_id}/filesFolder"
                        )
                        drive_id = files_data.get("parentReference", {}).get("driveId")
                        folder_id = files_data.get("id")
                        if drive_id and folder_id:
                            items_data = await graph_get(
                                token, f"/drives/{drive_id}/items/{folder_id}/children"
                            )
                            for item in items_data.get("value", []):
                                if not item.get("folder"):
                                    await _ingest_file(token, item, "teams", connector_id, results)
                    except Exception as e:
                        print(f"[M365/Teams] Channel error in {team_name}: {e}")
            except Exception as e:
                print(f"[M365/Teams] Team error {team_name}: {e}")
    except Exception as e:
        print(f"[M365/Teams] Error: {e}")
        results["errors"].append(f"Teams: {str(e)[:100]}")


async def run_m365_sync(connector_id: str) -> Dict[str, Any]:
    """Main sync entry point — syncs all selected sources."""
    connector = await get_m365_connector(connector_id)
    if not connector:
        return {"error": "Connector not found"}

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE m365_connectors SET status='syncing' WHERE id=:id"),
            {"id": connector_id}
        )
        await db.commit()

    results = {"synced": 0, "skipped": 0, "failed": 0, "errors": []}

    try:
        token = await get_access_token(
            connector["tenant_id"],
            connector["client_id"],
            connector["client_secret"],
        )
        print(f"[M365] Token acquired. Syncing sources: {connector['sources']}")

        sources = connector.get("sources", ["teams", "onedrive", "sharepoint"])

        if "onedrive" in sources:
            await sync_onedrive(token, connector_id, results)
        if "sharepoint" in sources:
            await sync_sharepoint(token, connector_id, results)
        if "teams" in sources:
            await sync_teams(token, connector_id, results)

        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                UPDATE m365_connectors
                SET status='idle', last_sync_at=NOW(),
                    files_synced = files_synced + :synced
                WHERE id=:id
            """), {"synced": results["synced"], "id": connector_id})
            await db.commit()

    except Exception as e:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE m365_connectors SET status='error' WHERE id=:id"),
                {"id": connector_id}
            )
            await db.commit()
        results["error"] = str(e)
        print(f"[M365] Sync failed: {e}")

    print(f"[M365] Complete: {results}")
    return results
