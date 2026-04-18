"""
IntelliRAG — On-premise AI knowledge assistant.
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, migrate_analytics
from app.core.vector_store import init_vector_store
from app.core.exceptions import IntelliRAGException, intellirag_exception_handler
from app.api.v1.router import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("intellirag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler."""
    logger.info("Starting IntelliRAG...")
    await init_db()
    await migrate_analytics()
    await init_vector_store()

    # ── Auto-sync: init tables then start scheduler ───────────────────────────
    try:
        from app.services.autosync_service import ensure_autosync_tables, start_autosync
        await ensure_autosync_tables()
        start_autosync()
        logger.info("Auto-sync scheduler started")
    except Exception as e:
        logger.warning(f"Auto-sync failed to start: {e}")

    logger.info("IntelliRAG is ready.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    try:
        from app.services.autosync_service import stop_autosync
        stop_autosync()
    except Exception:
        pass
    logger.info("IntelliRAG shutting down.")


app = FastAPI(
    title="IntelliRAG API",
    description="On-premise RAG platform — embed anywhere, zero data leakage",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(IntelliRAGException, intellirag_exception_handler)
app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "product": "IntelliRAG",
        "version": "2.0.0",
        "status": "running",
        "docs": "/api/docs",
    }
