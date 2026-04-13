from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.analytics import get_dashboard, save_feedback

router = APIRouter()


@router.get("/{tenant_slug}")
async def dashboard(tenant_slug: str):
    """
    Get full analytics dashboard for a tenant.
    GET /api/analytics/hr
    """
    try:
        data = await get_dashboard(tenant_slug)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FeedbackRequest(BaseModel):
    feedback: str  # "thumbs_up" or "thumbs_down"


@router.post("/feedback/{log_id}")
async def feedback(log_id: str, req: FeedbackRequest):
    """
    Save user feedback for a query.
    POST /api/analytics/feedback/<query_id>
    { "feedback": "thumbs_up" }
    """
    if req.feedback not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(status_code=400, detail="feedback must be thumbs_up or thumbs_down")
    await save_feedback(log_id, req.feedback)
    return {"status": "saved", "feedback": req.feedback}
