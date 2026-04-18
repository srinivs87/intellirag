"""
Audit Trail API
"""
import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

log = logging.getLogger("intellirag.audit")
router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("")
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
):
    offset = (page - 1) * per_page

    async with AsyncSessionLocal() as db:
        if search:
            s = f"%{search.lower()}%"
            count_row = await db.execute(
                text("SELECT COUNT(*) FROM query_logs WHERE LOWER(question) LIKE :s"),
                {"s": s}
            )
            total = count_row.scalar_one() or 0

            rows_result = await db.execute(text("""
                SELECT id, tenant_slug, question, answer, sources,
                       confidence_score, retrieval_ms, generation_ms, total_ms,
                       session_id, user_id, user_role, feedback, created_at
                FROM query_logs
                WHERE LOWER(question) LIKE :s
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """), {"s": s, "lim": per_page, "off": offset})
        else:
            count_row = await db.execute(
                text("SELECT COUNT(*) FROM query_logs")
            )
            total = count_row.scalar_one() or 0

            rows_result = await db.execute(text("""
                SELECT id, tenant_slug, question, answer, sources,
                       confidence_score, retrieval_ms, generation_ms, total_ms,
                       session_id, user_id, user_role, feedback, created_at
                FROM query_logs
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """), {"lim": per_page, "off": offset})

        rows = rows_result.fetchall()

    entries = []
    for row in rows:
        raw_sources = row[4]
        if isinstance(raw_sources, str):
            try:
                sources = json.loads(raw_sources)
            except Exception:
                sources = []
        elif isinstance(raw_sources, list):
            sources = raw_sources
        else:
            sources = []

        entries.append({
            "id": str(row[0]),
            "tenant_slug": row[1] or "general",
            "question": row[2] or "",
            "answer": (row[3] or "")[:500],
            "sources": sources,
            "confidence": round(float(row[5] or 0), 3),
            "retrieval_ms": int(row[6] or 0),
            "generation_ms": int(row[7] or 0),
            "total_ms": int(row[8] or 0),
            "session_id": str(row[9]) if row[9] else None,
            "user_id": row[10],
            "user_role": row[11],
            "feedback": row[12],
            "created_at": row[13].isoformat() if row[13] else None,
        })

    return {
        "entries": entries,
        "total": int(total),
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, -(-int(total) // per_page)),
    }


@router.get("/export")
async def export_audit_csv():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, tenant_slug, question, answer, sources,
                   confidence_score, total_ms, user_id, user_role,
                   feedback, created_at
            FROM query_logs
            ORDER BY created_at DESC
            LIMIT 10000
        """))
        rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "Tenant", "Question", "Answer",
        "Confidence %", "Response Time (ms)", "User ID", "User Role",
        "Sources Count", "Feedback"
    ])

    for row in rows:
        raw_sources = row[4]
        if isinstance(raw_sources, str):
            try:
                sources = json.loads(raw_sources)
            except Exception:
                sources = []
        elif isinstance(raw_sources, list):
            sources = raw_sources
        else:
            sources = []

        writer.writerow([
            str(row[0]),
            row[10].isoformat() if row[10] else "",
            row[1] or "general",
            row[2] or "",
            (row[3] or "").replace('\n', ' ')[:500],
            f"{round(float(row[5] or 0) * 100)}%",
            int(row[6] or 0),
            row[7] or "anonymous",
            row[8] or "user",
            len(sources),
            row[9] or "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=intellirag-audit.csv"},
    )
