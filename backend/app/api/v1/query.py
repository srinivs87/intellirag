"""
Query API — handles RAG queries with session memory.
"""
import uuid
from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag.pipeline import retrieve_and_generate, stream_retrieve_and_generate
from app.services.rag.generation import generate_answer
from app.services.memory import get_or_create_session, save_message, get_history, get_full_history, clear_session
from app.services.analytics import log_query

router = APIRouter()


@router.post("/", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    user_id = req.user_context.get("user_id") if req.user_context else None
    user_role = req.user_context.get("role") if req.user_context else None

    session_id = await get_or_create_session(req.session_id, req.tenant, user_id)
    history = await get_history(session_id, limit=4)

    result = await retrieve_and_generate(
        question=req.question,
        tenant_slug=req.tenant,
        top_k=req.top_k,
        user_context=req.user_context,
        history=history,
        sources=req.sources,
    )

    await save_message(session_id, "user", req.question)
    await save_message(session_id, "assistant", result["answer"])

    query_id = await log_query(
        tenant_slug=req.tenant,
        question=req.question,
        answer=result["answer"],
        sources=result["sources"],
        confidence_score=result["confidence"],
        retrieval_ms=result["retrieval_ms"],
        generation_ms=result["generation_ms"],
        total_ms=result["total_ms"],
        session_id=session_id,
        user_id=user_id,
        user_role=user_role,
    )

    return QueryResponse(query_id=query_id, session_id=session_id, **result)


@router.post("/stream")
async def query_stream(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    user_id = req.user_context.get("user_id") if req.user_context else None
    session_id = await get_or_create_session(req.session_id, req.tenant, user_id)
    history = await get_history(session_id, limit=4)
    full_answer = []

    async def event_generator():
        async for token in stream_retrieve_and_generate(
            question=req.question, tenant_slug=req.tenant, history=history,
        ):
            full_answer.append(token)
            yield f"data: {token}\n\n"

        answer_text = "".join(full_answer)
        await save_message(session_id, "user", req.question)
        await save_message(session_id, "assistant", answer_text)
        yield f"data: [SESSION:{session_id}]\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Session-Id": session_id},
    )


@router.get("/history/{session_id}")
async def get_conversation_history(session_id: str):
    messages = await get_full_history(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    await clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


class SuggestionsRequest(BaseModel):
    prompt: str


@router.post("/suggestions")
async def get_suggestions(req: SuggestionsRequest):
    """Generate follow-up question suggestions using Groq."""
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Return ONLY a valid JSON array of 3 short strings. No explanation, no markdown, just the array."},
            {"role": "user", "content": req.prompt}
        ]
        answer = await generate_answer(messages)
        # Clean and parse
        clean = answer.strip().replace('```json', '').replace('```', '').strip()
        import json
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            return {"suggestions": parsed[:3]}
        return {"suggestions": []}
    except Exception as e:
        print(f"[Suggestions] Error: {e}")
        return {"suggestions": []}
