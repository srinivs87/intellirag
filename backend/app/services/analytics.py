"""
Analytics Service
- Logs every query to PostgreSQL
- Provides dashboard metrics per tenant
- Handles thumbs up/down feedback
"""

import uuid
import json
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


async def ensure_analytics_columns():
    """Ensure tenant_slug and session_id columns exist on query_logs."""
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("""
                ALTER TABLE query_logs
                ADD COLUMN IF NOT EXISTS tenant_slug VARCHAR(50),
                ADD COLUMN IF NOT EXISTS session_id  UUID
            """))
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_query_logs_tenant_slug
                ON query_logs(tenant_slug)
            """))
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_query_logs_confidence
                ON query_logs(confidence_score)
            """))
            await db.commit()
        except Exception as e:
            print(f"[Analytics] Column check: {e}")


async def log_query(
    tenant_slug: str,
    question: str,
    answer: str,
    sources: list,
    confidence_score: float,
    retrieval_ms: int,
    generation_ms: int,
    total_ms: int,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_role: Optional[str] = None,
) -> str:
    """Log a completed query. Returns the log entry ID."""
    log_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(
                text("""
                    INSERT INTO query_logs (
                        id, tenant_slug, question, answer, sources,
                        confidence_score, retrieval_ms, generation_ms, total_ms,
                        session_id, user_id, user_role, created_at
                    ) VALUES (
                        :id, :tenant_slug, :question, :answer, :sources,
                        :confidence_score, :retrieval_ms, :generation_ms, :total_ms,
                        :session_id, :user_id, :user_role, NOW()
                    )
                """),
                {
                    "id": log_id,
                    "tenant_slug": tenant_slug,
                    "question": question,
                    "answer": answer,
                    "sources": json.dumps(sources),
                    "confidence_score": confidence_score,
                    "retrieval_ms": retrieval_ms,
                    "generation_ms": generation_ms,
                    "total_ms": total_ms,
                    "session_id": session_id,
                    "user_id": user_id,
                    "user_role": user_role,
                }
            )
            await db.commit()
        except Exception as e:
            print(f"[Analytics] Failed to log query: {e}")
            # Try to ensure columns exist and retry once
            await ensure_analytics_columns()
            try:
                async with AsyncSessionLocal() as db2:
                    await db2.execute(
                        text("""
                            INSERT INTO query_logs (
                                id, tenant_slug, question, answer, sources,
                                confidence_score, retrieval_ms, generation_ms, total_ms,
                                session_id, user_id, user_role, created_at
                            ) VALUES (
                                :id, :tenant_slug, :question, :answer, :sources,
                                :confidence_score, :retrieval_ms, :generation_ms, :total_ms,
                                :session_id, :user_id, :user_role, NOW()
                            )
                        """),
                        {
                            "id": log_id, "tenant_slug": tenant_slug,
                            "question": question, "answer": answer,
                            "sources": json.dumps(sources),
                            "confidence_score": confidence_score,
                            "retrieval_ms": retrieval_ms,
                            "generation_ms": generation_ms,
                            "total_ms": total_ms,
                            "session_id": session_id,
                            "user_id": user_id, "user_role": user_role,
                        }
                    )
                    await db2.commit()
            except Exception as e2:
                print(f"[Analytics] Retry also failed: {e2}")
    return log_id


async def save_feedback(log_id: str, feedback: str):
    """Save thumbs_up or thumbs_down feedback."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE query_logs SET feedback = :feedback WHERE id = :id"),
            {"feedback": feedback, "id": log_id}
        )
        await db.commit()


async def get_dashboard(tenant_slug: str) -> Dict[str, Any]:
    """Return all dashboard metrics for a tenant."""
    await ensure_analytics_columns()

    async with AsyncSessionLocal() as db:
        # Total queries
        r = await db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day')  AS today,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS this_week
            FROM query_logs WHERE tenant_slug = :t
        """), {"t": tenant_slug})
        counts = r.fetchone()

        # Averages
        r = await db.execute(text("""
            SELECT ROUND(AVG(confidence_score)::numeric, 2) AS avg_conf,
                   ROUND(AVG(total_ms)::numeric, 0)         AS avg_ms
            FROM query_logs WHERE tenant_slug = :t
        """), {"t": tenant_slug})
        avgs = r.fetchone()

        # Feedback
        r = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE feedback = 'thumbs_up')   AS thumbs_up,
                COUNT(*) FILTER (WHERE feedback = 'thumbs_down') AS thumbs_down
            FROM query_logs WHERE tenant_slug = :t
        """), {"t": tenant_slug})
        feedback = r.fetchone()

        # Top 5 questions
        r = await db.execute(text("""
            SELECT question, COUNT(*) AS count
            FROM query_logs WHERE tenant_slug = :t
            GROUP BY question ORDER BY count DESC LIMIT 5
        """), {"t": tenant_slug})
        top_questions = [{"question": row.question, "count": row.count} for row in r.fetchall()]

        # Low confidence
        r = await db.execute(text("""
            SELECT question, confidence_score, created_at
            FROM query_logs
            WHERE tenant_slug = :t AND confidence_score < 0.4
            ORDER BY created_at DESC LIMIT 10
        """), {"t": tenant_slug})
        unanswered = [
            {"question": row.question, "confidence": float(row.confidence_score or 0), "asked_at": row.created_at.isoformat()}
            for row in r.fetchall()
        ]

        # Recent queries
        r = await db.execute(text("""
            SELECT id, question, confidence_score, total_ms, feedback, created_at
            FROM query_logs WHERE tenant_slug = :t
            ORDER BY created_at DESC LIMIT 20
        """), {"t": tenant_slug})
        recent = [
            {"id": str(row.id), "question": row.question, "confidence": float(row.confidence_score or 0),
             "total_ms": row.total_ms, "feedback": row.feedback, "asked_at": row.created_at.isoformat()}
            for row in r.fetchall()
        ]

        return {
            "tenant": tenant_slug,
            "totals": {
                "all_time": int(counts.total) if counts else 0,
                "today": int(counts.today) if counts else 0,
                "this_week": int(counts.this_week) if counts else 0,
            },
            "averages": {
                "confidence": float(avgs.avg_conf or 0) if avgs else 0,
                "response_ms": int(avgs.avg_ms or 0) if avgs else 0,
            },
            "feedback": {
                "thumbs_up": int(feedback.thumbs_up) if feedback else 0,
                "thumbs_down": int(feedback.thumbs_down) if feedback else 0,
            },
            "top_questions": top_questions,
            "unanswered": unanswered,
            "recent_queries": recent,
        }
