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

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("intellirag")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler."""
    logger.info("Starting IntelliRAG...")
    await init_db()
    await migrate_analytics()
    await init_vector_store()
    logger.info("IntelliRAG is ready.")
    yield
    logger.info("IntelliRAG shutting down.")


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="IntelliRAG API",
    description="On-premise RAG platform — embed anywhere, zero data leakage",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception Handlers ────────────────────────────────────────────────────────
app.add_exception_handler(IntelliRAGException, intellirag_exception_handler)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root():
    return {"product": "IntelliRAG", "version": "2.0.0", "status": "running", "docs": "/api/docs"}
