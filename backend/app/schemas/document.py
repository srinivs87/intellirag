from pydantic import BaseModel
from typing import Optional


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    status: str = "success"
    chunks_created: int
    message: str = ""


class DocumentRecord(BaseModel):
    document_id: str
    filename: str
    tenant_slug: str
    uploaded_by: str
    chunks: int
    created_at: Optional[str] = None
