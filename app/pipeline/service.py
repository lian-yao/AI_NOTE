"""
Pipeline 服务：编排完整工作流。
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.database import SessionLocal
from app.core.paths import project_path
from app.models.video import Video
from app.models.note import Note
from app.models.chunk import Chunk
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
        """下载 -> 转写 -> 生成笔记 -> 切片存储。"""
        db = SessionLocal()
        try:
            # 1. 创建视频记录
            video_id_str = f"b_mock{int(__import__("time").time())}"
            video = Video(
                video_id=video_id_str,
                url=source_url,
                title="视频标题（Mock）",
                status="completed",
            )
            db.add(video)
            db.flush()

            # 2. 转写（按新协议：audio_path, video_dir, progress_cb -> StageResult）
            video_dir = str(project_path("data", "videos", video_id_str))
            Path(video_dir).mkdir(parents=True, exist_ok=True)
            audio_path = str(Path(video_dir) / "audio.wav")
            result = await self.transcriber.transcribe(audio_path, video_dir)

            if not result.success:
                raise RuntimeError(f"转写失败: {result.error}")

            transcript_text = result.metadata.get("full_text", "")
            segment_count = result.metadata.get("segment_count", 0)

            # 3. 写笔记文件
            notes_dir = project_path("data", "notes")
            notes_dir.mkdir(parents=True, exist_ok=True)
            note_file = notes_dir / f"{video.video_id}.md"
            note_content = await self.llm.chat(
                [
                    {"role": "system", "content": "根据以下转录文本生成结构化笔记："},
                    {"role": "user", "content": transcript_text},
                ]
            )
            note_file.write_text(note_content, encoding="utf-8")

            # 4. 创建笔记记录
            note = Note(
                video_id=video.id,
                file_path=str(note_file),
                summary="Mock 笔记摘要",
                keywords='["AI", "深度学习"]',
                total_chunks=segment_count,
                section_count=1,
                char_count=len(note_content),
                model_used="mock",
            )
            db.add(note)
            db.flush()

            # 5. 处理为文本切片并存储
            from app.schemas.transcript import TranscriptResult, TranscriptSegment
            mock_transcript = TranscriptResult(
                segments=[TranscriptSegment(text=transcript_text, start=0.0, end=1.0)],
                full_text=transcript_text,
                language=result.metadata.get("language", "zh"),
            )
            chunks = await self.processor.process(
                mock_transcript, note.id, video.video_id
            )
            await self.store.add_chunks(chunks)

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
