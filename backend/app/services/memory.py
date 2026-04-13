"""
Conversation Memory Service
- Stores conversation history in PostgreSQL
- Sessions expire after 7 days
- Returns last N messages for context injection
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

SESSION_TTL_DAYS = 7
MAX_HISTORY = 4  # last 4 messages injected into prompt


async def get_or_create_session(session_id: Optional[str], tenant_slug: str, user_id: Optional[str] = None) -> str:
    """
    Return existing session_id if valid and not expired,
    or create a new one.
    """
    async with AsyncSessionLocal() as db:
        if session_id:
            result = await db.execute(
                text("""
                    SELECT id FROM conversations
                    WHERE id = :sid
                      AND tenant_slug = :tenant
                      AND expires_at > NOW()
                """),
                {"sid": session_id, "tenant": tenant_slug}
            )
            row = result.fetchone()
            if row:
                # Refresh expiry on activity
                await db.execute(
                    text("UPDATE conversations SET expires_at = :exp, updated_at = NOW() WHERE id = :sid"),
                    {"exp": datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS), "sid": session_id}
                )
                await db.commit()
                return session_id

        # Create new session
        new_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO conversations (id, tenant_slug, user_id, created_at, updated_at, expires_at)
                VALUES (:id, :tenant, :user_id, NOW(), NOW(), :exp)
            """),
            {
                "id": new_id,
                "tenant": tenant_slug,
                "user_id": user_id,
                "exp": datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS),
            }
        )
        await db.commit()
        return new_id


async def save_message(session_id: str, role: str, content: str):
    """Save a single message (role: 'user' or 'assistant') to the conversation."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO messages (id, conversation_id, role, content, created_at)
                VALUES (:id, :conv_id, :role, :content, NOW())
            """),
            {
                "id": str(uuid.uuid4()),
                "conv_id": session_id,
                "role": role,
                "content": content,
            }
        )
        await db.commit()


async def get_history(session_id: str, limit: int = MAX_HISTORY) -> List[Dict]:
    """
    Fetch the last N messages for a session.
    Returns list of {"role": "user"|"assistant", "content": "..."}
    ordered oldest → newest (ready to inject into prompt).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT role, content FROM messages
                WHERE conversation_id = :sid
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"sid": session_id, "limit": limit}
        )
        rows = result.fetchall()
        # Reverse so oldest is first
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def get_full_history(session_id: str) -> List[Dict]:
    """Fetch all messages for a session (for UI rendering)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT role, content, created_at FROM messages
                WHERE conversation_id = :sid
                ORDER BY created_at ASC
            """),
            {"sid": session_id}
        )
        rows = result.fetchall()
        return [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
            for r in rows
        ]


async def clear_session(session_id: str):
    """Delete all messages for a session (New Conversation button)."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM messages WHERE conversation_id = :sid"),
            {"sid": session_id}
        )
        await db.execute(
            text("DELETE FROM conversations WHERE id = :sid"),
            {"sid": session_id}
        )
        await db.commit()


async def purge_expired_sessions():
    """Cleanup job — remove sessions older than TTL."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM conversations WHERE expires_at < NOW()"))
        await db.commit()
