"""
Q&A request/response schemas.
"""
from pydantic import BaseModel
from app.schemas.chunk import SearchResult


class QARequest(BaseModel):
    question: str
    note_id: str | None = None
    top_k: int = 5


class QAResponse(BaseModel):
    answer: str
    sources: list[SearchResult]
