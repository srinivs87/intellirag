"""
Personal OneDrive connector using Device Code Flow.
No Azure app changes needed — user authenticates via microsoft.com/device
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.services.ingestion import ingest_document

router = APIRouter()

TENANT_ID  = "d9e0bc23-1324-46dc-9d18-df127bdfc304"
CLIENT_ID  = "d7f0301c-b202-4cd4-a2f7-301a146aa70b"
CLIENT_SECRET = "ofV8Q~H3mlvWFYdZ3uSNmGnBcN7fyxkQKWk6JbuM"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPE      = "Files.Read offline_access User.Read"

SUPPORTED = {".pdf",".docx",".doc",".xlsx",".xls",".pptx",".ppt",".txt",".md"}

# ── DB helpers ────────────────────────────────────────────────────────────────

async def ensure_tables():
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS personal_od_tokens (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                upn         VARCHAR(200),
                access_token  TEXT,
                refresh_token TEXT,
                expires_at  TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS personal_od_files (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                file_id     VARCHAR(500) UNIQUE,
                filename    VARCHAR(500),
                web_url     TEXT,
                file_path   TEXT,
                document_id VARCHAR(200),
                modified_at TIMESTAMPTZ,
                synced_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.commit()


async def save_token(upn: str, access_token: str, refresh_token: str, expires_in: int):
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM personal_od_tokens"))
        await db.execute(text("""
            INSERT INTO personal_od_tokens (upn, access_token, refresh_token, expires_at)
            VALUES (:upn, :at, :rt, :ea)
        """), {"upn": upn, "at": access_token, "rt": refresh_token, "ea": expires_at})
        await db.commit()


async def get_token() -> Optional[str]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT access_token, refresh_token, expires_at FROM personal_od_tokens LIMIT 1"
        ))
        row = r.fetchone()
        if not row:
            return None
        # If not expired, return directly
        now = datetime.now(timezone.utc)
        exp = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
        if now < exp:
            return row.access_token
        # Refresh
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
                    data={"grant_type":"refresh_token","client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,
                          "refresh_token":row.refresh_token,"scope":SCOPE}
                )
                if resp.status_code == 200:
                    d = resp.json()
                    await save_token("", d["access_token"], d.get("refresh_token", row.refresh_token), d["expires_in"])
                    return d["access_token"]
        except Exception:
            pass
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/personal-od/start")
async def start_device_login():
    """Step 1: Get a device code for the user to enter at microsoft.com/device"""
    await ensure_tables()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode",
            data={"client_id": CLIENT_ID, "scope": SCOPE}
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=resp.text)
        d = resp.json()
        return {
            "user_code":        d["user_code"],
            "device_code":      d["device_code"],
            "verification_uri": d["verification_uri"],
            "expires_in":       d["expires_in"],
            "interval":         d.get("interval", 5),
            "message":          d["message"],
        }


@router.post("/personal-od/poll")
async def poll_for_token(body: dict, background_tasks: BackgroundTasks):
    """Step 2: Poll until user completes login, then store token and start sync."""
    device_code = body.get("device_code")
    interval    = int(body.get("interval", 5))
    if not device_code:
        raise HTTPException(status_code=400, detail="device_code required")

    deadline = 300  # 5 minutes max
    waited   = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < deadline:
            await asyncio.sleep(interval)
            waited += interval
            resp = await client.post(
                f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
                data={"grant_type":"urn:ietf:params:oauth:grant-type:device_code",
                      "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                      "device_code": device_code}
            )
            d = resp.json()
            if "access_token" in d:
                # Get user info
                me = await client.get(f"{GRAPH_BASE}/me",
                    headers={"Authorization": f"Bearer {d['access_token']}"})
                upn = me.json().get("userPrincipalName","") if me.status_code == 200 else ""
                await save_token(upn, d["access_token"],
                                 d.get("refresh_token",""), d["expires_in"])
                background_tasks.add_task(sync_personal_onedrive)
                return {"status": "authenticated", "upn": upn,
                        "message": "Authenticated! Syncing your OneDrive files now..."}
            if d.get("error") == "authorization_pending":
                continue
            raise HTTPException(status_code=400, detail=d.get("error_description", d.get("error")))
    raise HTTPException(status_code=408, detail="Login timed out — please try again")


@router.get("/personal-od/status")
async def get_status():
    """Check if personal OneDrive is connected and how many files are synced."""
    await ensure_tables()
    token = await get_token()
    async with AsyncSessionLocal() as db:
        r  = await db.execute(text("SELECT upn FROM personal_od_tokens LIMIT 1"))
        tr = r.fetchone()
        fr = await db.execute(text("SELECT COUNT(*) as cnt FROM personal_od_files"))
        fc = fr.fetchone()
    return {
        "connected":    token is not None,
        "upn":          tr.upn if tr else None,
        "files_synced": fc.cnt if fc else 0,
    }


@router.post("/personal-od/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    token = await get_token()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Use /start first.")
    background_tasks.add_task(sync_personal_onedrive)
    return {"status": "sync_started"}


@router.delete("/personal-od/disconnect")
async def disconnect():
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM personal_od_tokens"))
        await db.commit()
    return {"status": "disconnected"}


@router.get("/personal-od/files")
async def list_files():
    await ensure_tables()
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT filename, web_url, file_path, synced_at FROM personal_od_files ORDER BY filename"
        ))
        return {"files": [{"filename":row.filename,"web_url":row.web_url,
                           "file_path":row.file_path} for row in r.fetchall()]}


# ── Sync logic ────────────────────────────────────────────────────────────────

async def sync_personal_onedrive():
    """Sync all files from personal OneDrive into intellirag_onedrive collection."""
    token = await get_token()
    if not token:
        print("[PersonalOD] No token — skipping sync")
        return

    print("[PersonalOD] Starting sync...")
    synced = 0
    skipped = 0
    errors = 0

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        # Get all files recursively from root
        async def process_folder(path: str):
            nonlocal synced, skipped, errors
            resp = await client.get(f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"})
            if resp.status_code != 200:
                print(f"[PersonalOD] Folder error {path}: {resp.status_code}")
                return
            for item in resp.json().get("value", []):
                if item.get("folder"):
                    child_id  = item["id"]
                    drive_id  = item.get("parentReference",{}).get("driveId","")
                    await process_folder(f"/drives/{drive_id}/items/{child_id}/children")
                else:
                    await process_file(item, client)

        async def process_file(item: dict, client):
            nonlocal synced, skipped, errors
            fname = item.get("name","")
            if not any(fname.lower().endswith(ext) for ext in SUPPORTED):
                return
            file_id     = item["id"]
            modified_at = item.get("lastModifiedDateTime","")
            web_url     = item.get("webUrl","")

            # Check if already synced and unchanged
            async with AsyncSessionLocal() as db:
                r = await db.execute(text(
                    "SELECT modified_at FROM personal_od_files WHERE file_id=:fid"
                ), {"fid": file_id})
                row = r.fetchone()
                if row and row.modified_at:
                    stored = row.modified_at.replace(tzinfo=timezone.utc) \
                             if row.modified_at.tzinfo is None else row.modified_at
                    incoming = datetime.fromisoformat(modified_at.replace("Z","+00:00"))
                    if stored >= incoming:
                        # Update web_url if missing
                        if web_url:
                            await db.execute(text(
                                "UPDATE personal_od_files SET web_url=:u WHERE file_id=:f"
                            ), {"u": web_url, "f": file_id})
                            await db.commit()
                        skipped += 1
                        return

            try:
                download_url = item.get("@microsoft.graph.downloadUrl","")
                if not download_url:
                    drive_id = item.get("parentReference",{}).get("driveId","")
                    dl = await client.get(
                        f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/content",
                        headers={"Authorization": f"Bearer {token}"})
                    file_bytes = dl.content
                else:
                    dl = await client.get(download_url)
                    file_bytes = dl.content

                if not file_bytes:
                    errors += 1
                    return

                document_id = str(uuid.uuid4())
                parent_path = item.get("parentReference",{}).get("path","")
                if "root:" in parent_path:
                    parent_path = parent_path.split("root:")[-1]
                file_path = f"{parent_path}/{fname}" if parent_path else fname

                await ingest_document(
                    file_bytes=file_bytes,
                    filename=fname,
                    tenant_slug="onedrive",
                    document_id=document_id,
                    uploaded_by="personal_onedrive",
                    extra_metadata={"web_url": web_url, "file_path": file_path,
                                    "source_type": "onedrive"},
                )

                async with AsyncSessionLocal() as db:
                    await db.execute(text("""
                        INSERT INTO personal_od_files
                            (file_id, filename, web_url, file_path, document_id, modified_at)
                        VALUES (:fid,:fname,:url,:path,:docid,:mod)
                        ON CONFLICT (file_id) DO UPDATE
                        SET filename=EXCLUDED.filename, web_url=EXCLUDED.web_url,
                            file_path=EXCLUDED.file_path, document_id=EXCLUDED.document_id,
                            modified_at=EXCLUDED.modified_at, synced_at=NOW()
                    """), {"fid":file_id,"fname":fname,"url":web_url,"path":file_path,
                           "docid":document_id,
                           "mod":datetime.fromisoformat(modified_at.replace("Z","+00:00")) if modified_at else None})
                    await db.commit()

                synced += 1
                print(f"[PersonalOD] Synced: {fname}")

            except Exception as e:
                errors += 1
                print(f"[PersonalOD] Failed {fname}: {e}")

        await process_folder("/me/drive/root/children")

    print(f"[PersonalOD] Done — synced:{synced} skipped:{skipped} errors:{errors}")
