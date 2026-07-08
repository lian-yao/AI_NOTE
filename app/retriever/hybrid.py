# app/retriever/hybrid.py
import re
from collections import defaultdict
from typing import List, Dict, Optional
from app.store.vector import VectorStore
from app.store.embedder import EmbeddingConfigurationError
from app.core.logger import logger

class HybridRetriever:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        # 关键词索引：词 -> set of chunk_id
        self.inverted_index = defaultdict(set)
        # chunk_id -> 元数据缓存（用于构建结果）
        self.chunk_cache = {}

    def build_keyword_index(self, chunks: List[Dict]):
        """构建倒排索引（通常在存储时调用）"""
        for chunk in chunks:
            chunk_id = chunk["id"]
            content = chunk["document"]
            # 简单分词（按空格和标点）
            words = re.findall(r'\w+', content.lower())
            for word in words:
                self.inverted_index[word].add(chunk_id)
            self.chunk_cache[chunk_id] = chunk

    async def retrieve(self, query: str, note_id: Optional[str] = None, top_k: int = 5) -> List[Dict]:
        """混合检索返回 top_k 个文档片段。
        note_id 参数兼容 PipelineOrchestrator 调用约定（映射为 video_id 过滤）。
        """
        video_id = note_id
        # 1. 向量检索（由 ChromaDB 处理）
        filter = {"video_id": video_id} if video_id else None
        vector_results = []
        try:
            vector_results = await self.vector_store.similarity_search(query, top_k=top_k*2, filter=filter)
        except EmbeddingConfigurationError as exc:
            logger.warning(f"向量检索跳过：{exc}")
        except Exception as exc:
            logger.warning(f"向量检索失败，将使用关键词兜底: {exc}")
        # 2. 关键词检索
        keyword_results = self._keyword_search(query, top_k=top_k*2, video_id=video_id)
        try:
            persisted_keyword_results = await self.vector_store.keyword_search(
                query,
                top_k=top_k*2,
                filter=filter,
            )
            seen_ids = {item.get("id") for item in keyword_results}
            keyword_results.extend(
                item for item in persisted_keyword_results if item.get("id") not in seen_ids
            )
        except Exception as exc:
            logger.warning(f"关键词兜底检索失败: {exc}")
        try:
            db_keyword_results = self._db_keyword_search(query, top_k=top_k*2, video_id=video_id)
            seen_ids = {item.get("id") for item in keyword_results}
            keyword_results.extend(
                item for item in db_keyword_results if item.get("id") not in seen_ids
            )
        except Exception as exc:
            logger.warning(f"数据库关键词兜底检索失败: {exc}")
        # 3. RRF 融合
        combined = defaultdict(float)
        k = 60  # RRF 常数
        for rank, item in enumerate(vector_results):
            combined[item["id"]] += 1 / (k + rank + 1)  # rank from 0
        for rank, item in enumerate(keyword_results):
            combined[item["id"]] += 1 / (k + rank + 1)
        # 按分数降序
        sorted_ids = sorted(combined, key=combined.get, reverse=True)[:top_k]
        # 获取最终文档
        final_results = []
        for chunk_id in sorted_ids:
            # 从 vector_results 或 keyword_results 中找
            for item in vector_results + keyword_results:
                if item["id"] == chunk_id:
                    final_results.append(item)
                    break
        return final_results

    def _keyword_search(self, query: str, top_k: int, video_id: Optional[str] = None) -> List[Dict]:
        """简单关键词匹配（基于倒排索引）"""
        words = re.findall(r'\w+', query.lower())
        scores = defaultdict(float)
        for word in words:
            for chunk_id in self.inverted_index.get(word, []):
                # 如果 video_id 指定，只取该视频的
                if video_id:
                    # 这里需要检查 chunk_id 是否属于该 video，我们可以从缓存中获取
                    if self.chunk_cache.get(chunk_id, {}).get("metadata", {}).get("video_id") != video_id:
                        continue
                scores[chunk_id] += 1.0  # 词频累加
        # 排序取 top_k
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        results = []
        for cid in sorted_ids:
            if cid in self.chunk_cache:
                results.append(self.chunk_cache[cid])
            else:
                # 如果缓存没有，可能要从 vector_store 获取，这里先跳过
                pass
        return results

    def _db_keyword_search(self, query: str, top_k: int, video_id: Optional[str] = None) -> List[Dict]:
        """Keyword fallback over SQL chunks when remote embeddings are unavailable."""
        from app.core.database import SessionLocal
        from app.models.chunk import Chunk
        from app.models.video import Video

        db = SessionLocal()
        try:
            rows_query = db.query(Chunk, Video).join(Video, Chunk.video_id == Video.id)
            if video_id:
                rows_query = rows_query.filter(Video.video_id == video_id)
            rows = rows_query.order_by(Chunk.created_at.desc()).limit(2000).all()
        finally:
            db.close()

        if not rows:
            return []

        terms = self._keyword_terms(query)
        phrase = (query or "").strip().lower()
        scored: list[tuple[float, int]] = []
        for index, (chunk, video) in enumerate(rows):
            text = (chunk.content or "").lower()
            score = 0.0
            for term in terms:
                score += text.count(term) * (2.0 if len(term) > 1 else 1.0)
            if phrase and phrase in text:
                score += 8.0
            scored.append((score, index))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [item for item in scored if item[0] > 0][:top_k]
        if not selected:
            selected = scored[:top_k]

        results = []
        for score, index in selected:
            chunk, video = rows[index]
            results.append({
                "id": chunk.chunk_id,
                "document": chunk.content,
                "metadata": {
                    "video_id": video.video_id,
                    "video_title": video.title,
                    "section_title": chunk.section_title,
                    "chunk_index": chunk.chunk_index,
                    "start_time": chunk.start_time,
                    "end_time": chunk.end_time,
                },
                "distance": 1.0 / (score + 1.0) if score > 0 else 1.0,
            })
        return results

    @staticmethod
    def _keyword_terms(text: str) -> list[str]:
        lower = (text or "").lower()
        terms = re.findall(r"[a-z0-9_]+", lower)
        for run in re.findall(r"[\u4e00-\u9fff]+", lower):
            terms.extend(run)
            terms.extend(run[index:index + 2] for index in range(max(0, len(run) - 1)))
        return list(dict.fromkeys(term for term in terms if term.strip()))
