"""
Mock LLM 实现。
"""


class MockLLM:
    """返回固定内容的 Mock 大模型。"""

    async def chat(self, messages: list[dict], **kwargs) -> str:
        return (
            "## 摘要\n\n"
            "这段视频讨论了人工智能与深度学习的发展。\n\n"
            "## 要点\n\n"
            "- AI 正在改变世界\n"
            "- 深度学习可理解图像与语言\n"
            "- 未来十年将有更多突破"
        )

    async def stream_chat(self, messages: list[dict], **kwargs):
        answer = await self.chat(messages, **kwargs)
        for char in answer:
            yield char

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]
