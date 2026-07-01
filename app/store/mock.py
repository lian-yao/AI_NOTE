"""
Mock 向量存储实现。
"""
from app.schemas.chunk import ChunkBase, SearchResult


class MockStore:
    """基于内存的 Mock 向量数据库。"""

    def __init__(self):
        self._chunks: dict[str, list[ChunkBase]] = {}

    async def add_chunks(self, chunks: list[ChunkBase]) -> None:
        for c in chunks:
            note_key = str(c.note_id)
            self._chunks.setdefault(note_key, []).append(c)

    async def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        all_chunks = [c for clist in self._chunks.values() for c in clist]
        return [SearchResult(chunk=c, score=0.85) for c in all_chunks[:top_k]]

    async def delete_chunks(self, note_id: str) -> None:
        self._chunks.pop(note_id, None)
