# app/store/vector.py
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.store.embedder import EmbeddingClient
from app.store.chunker import semantic_chunk
import uuid

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.vector_db_path,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="video_notes",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = EmbeddingClient()

    async def store_note(self, video_id: str, note_markdown: str, video_title: str):
        """将笔记切片、向量化并存入 ChromaDB"""
        # 1. 语义切片
        chunks = semantic_chunk(note_markdown)
        if not chunks:
            return

        # 2. 准备数据
        ids = []
        documents = []
        metadatas = []
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{video_id}_{idx}"
            ids.append(chunk_id)
            documents.append(chunk["content"])
            metadatas.append({
                "video_id": video_id,
                "video_title": video_title,
                "section_title": chunk["title"],
                "chunk_index": idx,
                "start_time": chunk.get("start_time", 0),
                "end_time": chunk.get("end_time", 0),
            })

        # 3. 向量化
        embeddings = await self.embedder.embed(documents)

        # 4. 存入 ChromaDB
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )
        return len(ids)

    async def delete_vectors(self, video_id: str):
        """删除某个视频的所有向量"""
        # 先查询所有该 video_id 的 ID
        results = self.collection.get(where={"video_id": video_id})
        if results and results["ids"]:
            self.collection.delete(ids=results["ids"])
        return len(results["ids"]) if results else 0

    async def similarity_search(self, query: str, top_k: int = 5, filter: Optional[Dict] = None) -> List[Dict]:
        """向量相似度检索"""
        query_emb = await self.embedder.embed([query])
        results = self.collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            where=filter,
            include=["documents", "metadatas", "distances"]
        )
        # 组装结果
        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return items