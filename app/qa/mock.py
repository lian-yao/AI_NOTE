"""
Mock 问答引擎实现 —— 使用真实 LLM + 检索上下文来回答。
"""
from app.schemas.chunk import SearchResult
from app.llm import LLM
from app.core.logger import logger


class MockQA:
    """基于检索上下文 + 真实 LLM 的问答引擎。"""

    def __init__(self, llm: LLM):
        self._llm = llm

    async def answer(self, question: str, context: list[SearchResult]) -> str:
        """根据检索到的上下文片段，使用 LLM 生成回答。"""
        if not context:
            return "未找到相关笔记内容。"

        # 1. 构建上下文文本
        context_parts = []
        for i, result in enumerate(context, 1):
            chunk = result.chunk
            header = f"【片段 {i}】"
            if chunk.section_title:
                header += f" 章节：{chunk.section_title}"
            context_parts.append(f"{header}\n{chunk.content}")

        context_text = "\n\n".join(context_parts)

        system_prompt = """你是一个基于知识库的智能问答助手。

## 核心原则
1. 只使用提供的参考资料来回答问题
2. 参考资料中没有相关信息时，明确告知未找到
3. 用中文回答，语言简洁易懂

## 参考资料
{context_text}"""

        user_prompt = f"""## 问题
{question}

请基于参考资料回答上述问题。"""

        messages = [
            {"role": "system", "content": system_prompt.format(context_text=context_text)},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"MockQA 调用 LLM 回答问题：{question}")
        try:
            answer = await self._llm.chat(messages, temperature=0.3)
            return answer
        except Exception as e:
            logger.error(f"MockQA LLM 调用失败: {e}")
            return f"抱歉，回答问题时出错: {e}"
