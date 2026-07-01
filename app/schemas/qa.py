"""
问答请求/响应数据模型。
"""
from pydantic import BaseModel
from app.schemas.chunk import SearchResult


class QARequest(BaseModel):
    """问答请求。"""
    question: str
    note_id: str | None = None
    top_k: int = 5


class QAResponse(BaseModel):
    """问答响应。"""
    answer: str
    sources: list[SearchResult]
