"""
RBAC Authentication API
Handles user registration, login, JWT token issuance and validation.
Roles: admin | user | viewer
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text
import bcrypt as _bcrypt
import jwt

from app.core.database import AsyncSessionLocal
from app.core.config import settings

log    = logging.getLogger("intellirag.auth")
router = APIRouter()
bearer = HTTPBearer(auto_error=False)


JWT_SECRET = getattr(settings, "JWT_SECRET", "intellirag-secret-change-in-production")
JWT_EXPIRE = int(getattr(settings, "JWT_EXPIRE_HOURS", 24))
JWT_ALG    = "HS256"
VALID_ROLES = {"admin", "user", "viewer"}


async def ensure_tables():
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS intellirag_users (
                id            TEXT PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'user',
                tenant_slug   TEXT NOT NULL DEFAULT 'general',
                is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT NOW(),
                last_login    TIMESTAMP
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_connector_access (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL REFERENCES intellirag_users(id) ON DELETE CASCADE,
                connector    TEXT NOT NULL,
                can_read     BOOLEAN DEFAULT TRUE,
                granted_by   TEXT,
                granted_at   TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, connector)
            )
        """))
        await db.commit()


async def get_user_by_email(email: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT * FROM intellirag_users WHERE email = :email"),
            {"email": email.lower()}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT * FROM intellirag_users WHERE id = :id"),
            {"id": user_id}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_user_connectors(user_id: str, role: str) -> list:
    if role == "admin":
        return ["uploaded", "gdrive", "teams", "sharepoint", "onedrive", "localfs"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT connector FROM user_connector_access
            WHERE user_id = :uid AND can_read = TRUE
        """), {"uid": user_id})
        rows = result.fetchall()
        return [r[0] for r in rows] if rows else ["uploaded"]


def create_token(user: dict) -> str:
    payload = {
        "sub":    user["id"],
        "email":  user["email"],
        "name":   user["name"],
        "role":   user["role"],
        "tenant": user["tenant_slug"],
        "exp":    datetime.utcnow() + timedelta(hours=JWT_EXPIRE),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not credentials:
        return None
    return decode_token(credentials.credentials)


async def require_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(credentials.credentials)


async def require_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    user = await require_user(credentials)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "user"
    tenant_slug: str = "general"

class LoginRequest(BaseModel):
    email: str
    password: str

class UpdateRoleRequest(BaseModel):
    role: str

class ConnectorAccessRequest(BaseModel):
    connectors: list


@router.post("/api/auth/register")
async def register(req: RegisterRequest):
    await ensure_tables()
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be: {VALID_ROLES}")
    if await get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM intellirag_users"))
        count = result.scalar()
        role = "admin" if count == 0 else req.role

    user_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO intellirag_users (id, email, name, password_hash, role, tenant_slug)
            VALUES (:id, :email, :name, :hash, :role, :tenant)
        """), {"id": user_id, "email": req.email.lower(), "name": req.name,
               "hash": _bcrypt.hashpw(req.password[:72].encode(), _bcrypt.gensalt()).decode(), "role": role, "tenant": req.tenant_slug})
        await db.commit()

    user = await get_user_by_id(user_id)
    token = create_token(user)
    log.info(f"[Auth] Registered: {req.email} as {role}")
    return {"token": token, "user": {"id": user["id"], "email": user["email"],
                                      "name": user["name"], "role": user["role"]}}


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    await ensure_tables()
    user = await get_user_by_email(req.email)
    if not user or not _bcrypt.checkpw(req.password[:72].encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account disabled")

    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE intellirag_users SET last_login = NOW() WHERE id = :id"),
                         {"id": user["id"]})
        await db.commit()

    connectors = await get_user_connectors(user["id"], user["role"])
    token = create_token(user)
    log.info(f"[Auth] Login: {req.email} ({user['role']})")
    return {"token": token, "user": {"id": user["id"], "email": user["email"],
                                      "name": user["name"], "role": user["role"],
                                      "connectors": connectors}}


@router.get("/api/auth/me")
async def me(current_user: dict = Depends(require_user)):
    connectors = await get_user_connectors(current_user["sub"], current_user["role"])
    return {"id": current_user["sub"], "email": current_user["email"],
            "name": current_user["name"], "role": current_user["role"],
            "connectors": connectors}


@router.get("/api/auth/users")
async def list_users(admin: dict = Depends(require_admin)):
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, email, name, role, tenant_slug, is_active, created_at, last_login
            FROM intellirag_users ORDER BY created_at DESC
        """))
        rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


@router.patch("/api/auth/users/{user_id}/role")
async def update_role(user_id: str, req: UpdateRoleRequest, admin: dict = Depends(require_admin)):
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE intellirag_users SET role = :role WHERE id = :id"),
                         {"role": req.role, "id": user_id})
        await db.commit()
    return {"status": "updated", "user_id": user_id, "role": req.role}


@router.patch("/api/auth/users/{user_id}/connectors")
async def set_connector_access(user_id: str, req: ConnectorAccessRequest,
                                admin: dict = Depends(require_admin)):
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM user_connector_access WHERE user_id = :uid"),
                         {"uid": user_id})
        for connector in req.connectors:
            await db.execute(text("""
                INSERT INTO user_connector_access (id, user_id, connector, granted_by)
                VALUES (:id, :uid, :connector, :granted_by)
            """), {"id": str(uuid.uuid4()), "uid": user_id,
                   "connector": connector, "granted_by": admin["sub"]})
        await db.commit()
    return {"status": "updated", "user_id": user_id, "connectors": req.connectors}


@router.delete("/api/auth/users/{user_id}")
async def deactivate_user(user_id: str, admin: dict = Depends(require_admin)):
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE intellirag_users SET is_active = FALSE WHERE id = :id"),
                         {"id": user_id})
        await db.commit()
    return {"status": "deactivated", "user_id": user_id}
