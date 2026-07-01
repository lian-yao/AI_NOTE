"""
Mock 问答引擎实现。
"""
from app.schemas.chunk import SearchResult
from app.llm import LLM


class MockQA:
    """基于 MockLLM 的简单问答引擎。"""

    def __init__(self, llm: LLM):
        self._llm = llm

    async def answer(self, question: str, context: list[SearchResult]) -> str:
        return f"根据相关内容，「{question}」是一个重要的发展方向。"
