"""
LLM protocol: chat completion & embedding.
"""
from __future__ import annotations
from typing import Protocol


class LLM(Protocol):
    """Large Language Model interface."""

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
