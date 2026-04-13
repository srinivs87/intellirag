from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


@router.get("/")
async def list_tenants():
    """Single unified knowledge base — no tenant separation."""
    return [
        {"slug": "general", "name": "General", "description": "Unified knowledge base — searches all connected sources"},
    ]


@router.post("/")
async def create_tenant(tenant: TenantCreate):
    from app.core.vector_store import ensure_collection
    collection = await ensure_collection(tenant.slug)
    return {"slug": tenant.slug, "name": tenant.name, "collection": collection, "status": "created"}
