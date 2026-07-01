"""
LLM 协议：对话补全与向量嵌入。
"""
from __future__ import annotations
from typing import Protocol


class LLM(Protocol):
    """大语言模型接口。"""

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        """对话补全。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化。"""
