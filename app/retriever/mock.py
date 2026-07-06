"""
Mock 检索器实现 —— 按 note_id(video_id) 过滤，完整返回匹配的笔记内容。
"""
from app.schemas.chunk import SearchResult
from app.store import Store


class MockRetriever:
    """基于 MockStore 的简单检索器。"""

    def __init__(self, store: Store):
        self._store = store

    async def retrieve(
        self, query: str, note_id: str | None = None, top_k: int = 5
    ) -> list[SearchResult]:
        # 获取该 video_id 下的所有 chunks（MockStore._chunks 以 video_id 为 key）
        if note_id and hasattr(self._store, "_chunks"):
            chunks = self._store._chunks.get(note_id, [])
            return [SearchResult(chunk=c, score=0.9) for c in chunks[:top_k]]
        # 没有指定 note_id 时返回所有
        return await self._store.search([0.0] * 4, top_k)
