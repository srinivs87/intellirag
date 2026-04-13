from pydantic import BaseModel
from typing import Optional, Dict, List


class QueryRequest(BaseModel):
    tenant: str = "general"
    question: str
    session_id: Optional[str] = None
    top_k: Optional[int] = None
    user_context: Optional[Dict] = None
    sources: Optional[List[str]] = None


class SourceReference(BaseModel):
    filename: str
    document_id: str
    chunk_index: int
    relevance_score: float
    web_url: Optional[str] = ""
    file_path: Optional[str] = ""
    source_type: Optional[str] = ""


class QueryResponse(BaseModel):
    query_id: str
    session_id: str
    answer: str
    sources: List[SourceReference]
    confidence: float
    retrieval_ms: int
    generation_ms: int
    total_ms: int
    chunks_used: int
