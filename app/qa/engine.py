import json, re, asyncio
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

    async def _analyze_question(self, query: str) -> list[str]:
        """Step 1: 将用户问题拆解为多个搜索查询，覆盖不同角度。"""
        system_prompt = """你是一个问题分析助手。将用户的问题分解为多个搜索查询，以便从知识库中检索相关信息。

返回 JSON 格式，如：
{"search_queries": ["查询1", "查询2"]}

要求：
- 每个查询从不同角度覆盖用户问题
- 查询简洁具体，适合向量检索
- 生成 2-3 个查询"""
        user_prompt = f"请分析以下问题，生成搜索查询：\n{query}"
        try:
            resp = await self.llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], temperature=0.1)
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            if m:
                data = json.loads(m.group())
                queries = data.get("search_queries", [])
                if queries:
                    logger.info(f"qa_analyze: {query[:40]} -> {queries}")
                    return queries
        except Exception as e:
            logger.warning(f"qa_analyze 失败，回退到原始查询: {e}")
        return [query]

    @staticmethod
    def _deduplicate_chunks(chunks: list[dict], top_k: int) -> list[dict]:
        """按文档内容去重，保留前 top_k 个。"""
        seen = set()
        result = []
        for c in chunks:
            doc = c.get("document", "")
            if doc not in seen:
                seen.add(doc)
                result.append(c)
        return result[:top_k]

    async def ask(
        self,
        query: str,
        mode: str = "global",
        video_id: Optional[str] = None,
        top_k: int = 5,
        llm: Optional[LLMClient] = None,
        history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """多步推理问答：拆解问题 → 多角度检索 → 综合分析 → 流式回答"""
        active_llm = llm or self.llm

        # Step 1: 拆解问题为多个搜索查询
        yield "正在分析问题..."
        search_queries = await self._analyze_question(query)

        # Step 2: 多角度并行检索
        yield "\n正在检索相关笔记..."
        all_chunks = []
        retrieve_tasks = [
            self.retriever.retrieve(sq, top_k=top_k, note_id=video_id if mode == "single" else None)
            for sq in search_queries
        ]
        results = await asyncio.gather(*retrieve_tasks)
        for chunks in results:
            all_chunks.extend(chunks)
        chunks = self._deduplicate_chunks(all_chunks, top_k)

        if not chunks:
            yield "\n未找到相关内容。"
            yield "参考文献：无"
            return

        # 构建上下文
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

        # Step 3: 构建 Prompt 进行综合分析
        yield "\n正在生成回答...\n\n"
        system_prompt = """你是一个基于知识库的智能问答助手。
## 核心原则
1. 只使用提供的参考资料来回答问题
2. 参考资料中没有相关信息时，明确告知未找到
3. 先综合分析各片段信息，再组织回答；如果问题有多个方面，逐一回应
4. 用自己的话综合回答，不要大段摘抄原文
5. 不要在正文中输出引用来源列表、引用脚注或 blockquote 原文引用；界面会在回答下方单独展示可折叠引用
6. 用中文回答，语言简洁易懂"""

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
            {"role": "user", "content": user_prompt},
        ]

        # Step 4: 流式调用 LLM
        _m = getattr(active_llm, 'model', '?')
        logger.info(f"qa: model={active_llm.__class__.__name__}({_m})")
        logger.info(f"qa: request={query[:80]}, queries={search_queries}")
        async for token in active_llm.stream_chat(messages, temperature=0.3):
            yield token

        # Step 5: 输出引用来源
        yield "\n\n---\n**引用来源**：\n"
        for ref in references:
            yield f"- 《{ref['video_title']}》- {ref['section_title']} (时间: {ref['start_time']}s)\n"

    async def answer(self, question: str, context: list, llm: Optional[LLMClient] = None) -> str:
        """Non-streaming QA: collect stream output and return full answer."""
        answer_parts = []
        async for token in self.ask(question, mode="global", llm=llm):
            answer_parts.append(token)
        return "".join(answer_parts)
