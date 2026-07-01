"""
Chunk and search result schemas for vector store & retrieval.
"""
from pydantic import BaseModel


class Chunk(BaseModel):
    note_id: str
    content: str
    chunk_index: int = 0
    embedding: list[float] | None = None
    metadata: dict | None = None


class SearchResult(BaseModel):
    chunk: Chunk
    score: float
