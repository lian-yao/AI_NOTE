# app/store/embedder.py
import httpx
from typing import List, Optional
from app.core.config import settings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when remote embedding is requested without an API key."""


class EmbeddingClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = (api_key or settings.embedding_api_key or settings.tongyi_api_key or "").strip()
        self.model = model or self._load_embedding_model() or settings.embedding_model
        self.openai_compatible = bool(base_url)
        if base_url:
            base = base_url.rstrip("/")
            self.base_url = base if base.endswith("/embeddings") else f"{base}/embeddings"
        else:
            self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    @staticmethod
    def _load_embedding_model() -> str | None:
        import json
        from pathlib import Path
        try:
            p = Path(settings.data_dir) / "embedding_config.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8")).get("model")
        except:
            pass
        return None

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本向量化
        :param texts: 文本列表
        :return: 向量列表
        """
        if not texts:
            return []
        if not self.api_key:
            raise EmbeddingConfigurationError(
                "Embedding API Key 未配置，请设置 VN_EMBEDDING_API_KEY 或 VN_TONGYI_API_KEY"
            )
        if self.openai_compatible:
            async with httpx.AsyncClient(timeout=120, verify=False) as client:
                response = await client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("data") or []
                items = sorted(items, key=lambda item: item.get("index", 0))
                return [item["embedding"] for item in items]

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
