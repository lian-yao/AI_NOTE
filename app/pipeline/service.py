"""
Pipeline 服务：编排完整工作流。
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.database import SessionLocal
from app.models.video import Video
from app.models.note import Note
from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse

from app.transcriber.mock import MockTranscriber
from app.processor.mock import MockProcessor
from app.llm.mock import MockLLM
from app.store.mock import MockStore
from app.retriever.mock import MockRetriever
from app.qa.mock import MockQA

if TYPE_CHECKING:
    from app.transcriber import Transcriber
    from app.processor import Processor
    from app.llm import LLM
    from app.store import Store
    from app.retriever import Retriever
    from app.qa import QAEngine


class PipelineService:
    """编排视频处理与问答的全流程。"""

    def __init__(
        self,
        transcriber: Transcriber | None = None,
        processor: Processor | None = None,
        llm: LLM | None = None,
        store: Store | None = None,
        retriever: Retriever | None = None,
        qa: QAEngine | None = None,
    ):
        self.transcriber = transcriber or MockTranscriber()
        self.processor = processor or MockProcessor()
        self.llm = llm or MockLLM()
        self.store = store or MockStore()
        self.retriever = retriever or MockRetriever(self.store)
        self.qa = qa or MockQA(self.llm)

    async def process_video(self, source_url: str) -> NoteResponse:
        """下载 -> 转写 -> 切块 -> 存储 -> 生成笔记。"""
        import uuid
        from datetime import datetime

        db = SessionLocal()
        try:
            # 1. 创建视频记录
            video = Video(
                id=str(uuid.uuid4()),
                source_url=source_url,
                title="视频标题（Mock）",
                status="completed",
            )
            db.add(video)
            db.flush()

            # 2. 转写
            audio_path = Path("./data/mock_audio.mp3")
            transcript = await self.transcriber.transcribe(audio_path)

            # 3. 创建笔记
            note = Note(
                id=str(uuid.uuid4()),
                video_id=video.id,
                title=f"{video.title} 的笔记",
                raw_transcript=transcript.full_text,
            )
            db.add(note)
            db.flush()

            # 4. 处理为文本块
            chunks = await self.processor.process(transcript, note.id)

            # 5. 向量化并存储
            embeddings = await self.llm.embed([c.content for c in chunks])
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb
            await self.store.add_chunks(chunks)

            # 6. 生成笔记内容
            note.content = await self.llm.chat(
                [
                    {"role": "system", "content": "根据以下转录文本生成结构化笔记："},
                    {"role": "user", "content": transcript.full_text},
                ]
            )
            db.commit()
            db.refresh(note)

            return NoteResponse.model_validate(note)
        finally:
            db.close()

    async def answer_question(self, request: QARequest) -> QAResponse:
        """检索相关文本块 -> 生成回答。"""
        context = await self.retriever.retrieve(
            request.question, request.note_id, request.top_k
        )
        answer = await self.qa.answer(request.question, context)
        return QAResponse(answer=answer, sources=context)
