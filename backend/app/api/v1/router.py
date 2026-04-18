"""
API v1 Router — aggregates all versioned endpoints.
"""
from fastapi import APIRouter

from app.api.v1 import (
    audit_api,
    autosync_api,
    attachment_query,
    registry_api,
    health, auth, query, ingest, analytics,
    connectors, m365, onedrive_personal, localfs, tenants, widget,
)

router = APIRouter()

# ── Core ──────────────────────────────────────────────────────────────────────
router.include_router(health.router,    prefix="/health",         tags=["Health"])
router.include_router(query.router,     prefix="/api/query",      tags=["Query"])
router.include_router(analytics.router, prefix="/api/analytics",  tags=["Analytics"])
router.include_router(tenants.router,   prefix="/api/tenants",    tags=["Tenants"])
router.include_router(ingest.router,    prefix="/api/ingest",     tags=["Ingestion"])
router.include_router(widget.router,    prefix="/widget",         tags=["Widget"])

# ── Auth ──────────────────────────────────────────────────────────────────────
router.include_router(auth.router, tags=["Auth"])

# ── Connectors ────────────────────────────────────────────────────────────────
router.include_router(connectors.router,          prefix="/api/connectors", tags=["Google Drive"])
router.include_router(m365.router,                prefix="/api/connectors", tags=["Microsoft 365"])
router.include_router(onedrive_personal.router,   prefix="/api/connectors", tags=["OneDrive Personal"])
router.include_router(localfs.router,                                        tags=["Local FS"])
router.include_router(attachment_query.router)
router.include_router(registry_api.router,                                    tags=["Registry"])

router.include_router(autosync_api.router)

router.include_router(audit_api.router)
