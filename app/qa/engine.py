# app/qa/engine.py
from typing import AsyncGenerator, Optional, List, Dict
from app.llm.client import get_llm_client, LLMClient
from app.llm.mock import MockLLM
from app.retriever.hybrid import HybridRetriever
from app.core.config import settings
from app.core.logger import logger

class QAEngine:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        if not settings.tongyi_api_key and not settings.deepseek_api_key:
            logger.warning("未配置全局 LLM API Key，问答默认 LLM 将使用 MockLLM")
            self.llm = MockLLM()
        else:
            try:
                self.llm = get_llm_client()
            except Exception as exc:
                logger.warning(f"全局问答 LLM 初始化失败，将使用 MockLLM: {exc}")
                self.llm = MockLLM()

    async def ask(
        self,
        query: str,
        mode: str = "global",
        video_id: Optional[str] = None,
        top_k: int = 5,
        llm: Optional[LLMClient] = None,
        history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成回答，最后 yield 引用信息"""
        # 1. 检索相关片段
        chunks = await self.retriever.retrieve(query, top_k=top_k, note_id=video_id if mode=="single" else None)
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
3. 用自己的话综合回答，不要大段摘抄原文
4. 不要在正文中输出引用来源列表、引用脚注或 blockquote 原文引用；界面会在回答下方单独展示可折叠引用
5. 用中文回答，语言简洁易懂"""

        user_prompt = f"""## 参考资料
{context_text}

---

## 问题
{query}

请基于参考资料回答上述问题。"""

        history_messages = []
        for item in (history or [])[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                history_messages.append({"role": role, "content": content})

        messages = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": user_prompt}
        ]

        # 4. 流式调用 LLM
        active_llm = llm or self.llm
        _m = getattr(active_llm, 'model', '?')
        logger.info(f"qa: model={active_llm.__class__.__name__}({_m})")
        logger.info(f"qa: request={query[:80]}")
        answer_parts = []
        async for token in active_llm.stream_chat(messages, temperature=0.3):
            answer_parts.append(token)
            yield token

        # 5. 最后输出引用来源（作为特殊标记）
        yield "\n\n---\n**引用来源**：\n"
        for ref in references:
            yield f"- 《{ref['video_title']}》- {ref['section_title']} (时间: {ref['start_time']}s)\n"
    async def answer(self, question: str, context: list, llm: Optional[LLMClient] = None) -> str:
        """Non-streaming QA: collect stream output and return full answer."""
        answer_parts = []
        async for token in self.ask(question, mode="global", llm=llm):
            answer_parts.append(token)
        return "".join(answer_parts)

