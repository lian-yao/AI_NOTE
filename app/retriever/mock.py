"""
Mock 检索器实现。
"""
from app.schemas.chunk import SearchResult
from app.store import Store


class MockRetriever:
    """基于 MockStore 的简单检索器。"""

    def __init__(self, store: Store):
        self._store = store

    async def retrieve(self, query: str, note_id: str | None = None, top_k: int = 5) -> list[SearchResult]:
        return await self._store.search([0.0] * 4, top_k)
