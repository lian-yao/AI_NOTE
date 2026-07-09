"""
Mock LLM 实现。
"""


class MockLLM:
    """返回固定内容的 Mock 大模型。"""

    async def chat(self, messages: list[dict], **kwargs) -> str:
        return (
            "## 摘要\n\n"
            "生成失败。\n\n"
            "## 要点\n\n"
            "- 检查apikey是否可以使用\n"
            "- 失败\n"

        )

    async def stream_chat(self, messages: list[dict], **kwargs):
        answer = await self.chat(messages, **kwargs)
        for char in answer:
            yield char

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]
