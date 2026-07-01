# app/store/embedder.py
import httpx
from typing import List, Optional
from app.core.config import settings

class EmbeddingClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.embedding_api_key or settings.tongyi_api_key
        self.model = model or settings.embedding_model
        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本向量化
        :param texts: 文本列表
        :return: 向量列表
        """
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": {"texts": texts}}
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data["output"]["embeddings"]]
            return embeddings