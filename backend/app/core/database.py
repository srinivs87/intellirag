from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings
import asyncio

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    for attempt in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                # ── Conversation memory ────────────────────────────────────────
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id          UUID PRIMARY KEY,
                        tenant_slug VARCHAR(50) NOT NULL,
                        user_id     VARCHAR(100),
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ DEFAULT NOW(),
                        expires_at  TIMESTAMPTZ NOT NULL
                    )
                """))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id              UUID PRIMARY KEY,
                        conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
                        role            VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
                        content         TEXT NOT NULL,
                        created_at      TIMESTAMPTZ DEFAULT NOW()
                    )
                """))

                # ── Query analytics ────────────────────────────────────────────
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS query_logs (
                        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        tenant_slug      VARCHAR(50),
                        tenant_id        UUID,
                        question         TEXT NOT NULL,
                        answer           TEXT,
                        sources          JSONB,
                        confidence_score FLOAT,
                        retrieval_ms     INT,
                        generation_ms    INT,
                        total_ms         INT,
                        session_id       UUID,
                        user_id          VARCHAR(100),
                        user_role        VARCHAR(100),
                        feedback         VARCHAR(20),
                        created_at       TIMESTAMPTZ DEFAULT NOW()
                    )
                """))

                # ── Local FS sync tracking ─────────────────────────────────────
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS localfs_synced_files (
                        id          TEXT PRIMARY KEY,
                        file_path   TEXT UNIQUE NOT NULL,
                        filename    TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        tenant_slug TEXT NOT NULL DEFAULT 'general',
                        file_date   TEXT,
                        hostname    TEXT,
                        synced_at   TIMESTAMP DEFAULT NOW()
                    )
                """))

                # ── Document Registry (Layer 3) ────────────────────────────────
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS document_registry (
                        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                        filename    TEXT NOT NULL,
                        collection  TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        file_type   TEXT,
                        file_path   TEXT,
                        summary     TEXT,
                        topics      TEXT[],
                        entities    TEXT[],
                        chunk_count INT DEFAULT 0,
                        synced_at   TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (document_id, collection)
                    )
                """))

                # ── Indexes ────────────────────────────────────────────────────
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversations_tenant ON conversations(tenant_slug)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversations_expires ON conversations(expires_at)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at DESC)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_query_logs_tenant_slug ON query_logs(tenant_slug)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_query_logs_created ON query_logs(created_at DESC)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_registry_filename ON document_registry(filename)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_registry_collection ON document_registry(collection)"))

            print("[DB] Connected and all tables ready")
            return

        except Exception as e:
            print(f"[DB] Attempt {attempt+1}/10 failed: {e}")
            await asyncio.sleep(3)

    print("[DB] Warning: Could not connect, continuing anyway")


async def migrate_analytics():
    """Add columns if they don't exist — safe to run multiple times."""
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("""
                ALTER TABLE query_logs
                ADD COLUMN IF NOT EXISTS tenant_slug VARCHAR(50),
                ADD COLUMN IF NOT EXISTS session_id  UUID
            """))
            await db.commit()
            print("[DB] Analytics migration complete")
        except Exception as e:
            print(f"[DB] Migration note: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
