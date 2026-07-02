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
    async def store_note(self, video_id: str, note_markdown: str, video_title: str) -> int:
        """Mock 存储笔记：切片后存入内存字典。

        模拟 VectorStore.store_note 的行为，
        不依赖 ChromaDB / EmbeddingClient。
        """
        from app.store.chunker import semantic_chunk
        chunks = semantic_chunk(note_markdown)
        chunk_bases = []
        for idx, chunk in enumerate(chunks):
            chunk_bases.append(ChunkBase(
                chunk_id=f"{video_id}_{idx}",
                video_id=0,
                note_id=hash(video_id) % 10000,
                content=chunk["content"],
                chunk_index=idx,
                section_title=chunk["title"],
                start_time=chunk.get("start_time", 0),
                end_time=chunk.get("end_time", 0),
            ))
        self._chunks[video_id] = chunk_bases
        return len(chunks)
