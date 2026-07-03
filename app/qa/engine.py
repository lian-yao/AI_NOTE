# app/qa/engine.py
from typing import AsyncGenerator, Optional, List, Dict
from app.llm.client import get_llm_client
from app.retriever.hybrid import HybridRetriever
from app.core.logger import logger

class QAEngine:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        self.llm = get_llm_client()

    async def ask(self, query: str, mode: str = "global", video_id: Optional[str] = None,
                  top_k: int = 5) -> AsyncGenerator[str, None]:
        """流式生成回答，最后 yield 引用信息"""
        # 1. 检索相关片段
        chunks = await self.retriever.retrieve(query, top_k=top_k, video_id=video_id if mode=="single" else None)
        if not chunks:
            yield "未找到相关内容。"
            yield "参考文献：无"
            return

        # 2. 构建上下文
        context_text = ""
        references = []
        for idx, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {})
            context_text += f"【片段{idx+1}】来自《{meta.get('video_title', '未知视频')}》章节《{meta.get('section_title', '')}》\n{chunk['document']}\n\n"
            references.append({
                "video_id": meta.get("video_id"),
                "video_title": meta.get("video_title"),
                "section_title": meta.get("section_title"),
                "content": chunk["document"],
                "start_time": meta.get("start_time"),
                "end_time": meta.get("end_time"),
            })

        # 3. 构建 Prompt
        system_prompt = """你是一个基于知识库的智能问答助手。
## 核心原则
1. 只使用提供的参考资料来回答问题
2. 参考资料中没有相关信息时，明确告知未找到
3. 在回答中标注引用来源（视频标题 + 章节）
4. 用中文回答，语言简洁易懂
## 引用格式
> 引用内容
> -- 来源：《视频标题》- 章节名称"""

        user_prompt = f"""## 参考资料
{context_text}

---

## 问题
{query}

请基于参考资料回答上述问题。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 4. 流式调用 LLM
        logger.info(f"问答请求：{query}")
        answer_parts = []
        async for token in self.llm.stream_chat(messages, temperature=0.3):
            answer_parts.append(token)
            yield token

        # 5. 最后输出引用来源（作为特殊标记）
        yield "\n\n---\n**引用来源**：\n"
        for ref in references:
            yield f"- 《{ref['video_title']}》- {ref['section_title']} (时间: {ref['start_time']}s)\n"
    async def answer(self, question: str, context: list) -> str:
        """Non-streaming QA: collect stream output and return full answer."""
        answer_parts = []
        async for token in self.ask(question, mode="global"):
            answer_parts.append(token)
        return "".join(answer_parts)

