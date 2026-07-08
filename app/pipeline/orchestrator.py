"流水线编排器：任务队列、并发控制、阶段编排。"

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from app.core.database import SessionLocal
from app.core.paths import project_path
from app.core.logger import logger
from app.models.chunk import Chunk
from app.models.video import Video
from app.models.note import Note
from app.models.task import Task as TaskModel
from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse

from app.transcriber import Transcriber
from app.processor import Processor
from app.processor import VideoProcessor
from app.llm import LLM
from app.store import Store
from app.retriever import Retriever
from app.qa import QAEngine

from app.transcriber.mock import MockTranscriber
from app.transcriber.bjian import BjianTranscriber
from app.processor.mock import MockProcessor
from app.store.vector import VectorStore
from app.llm.mock import MockLLM
from app.store.mock import MockStore
from app.retriever.mock import MockRetriever
from app.qa.mock import MockQA
from app.note.timeline import timestamp_from_seconds


class PipelineStage(str, Enum):
    "流水线处理阶段。"
    PARSE = "parse"
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    GENERATE = "generate"
    STORE = "store"

    def label(self) -> str:
        return {"parse": "解析链接", "download": "下载视频", "transcribe": "语音转写", "generate": "生成笔记", "store": "存储索引"}[self.value]

    def progress_weight(self) -> int:
        return {"parse": 5, "download": 20, "transcribe": 35, "generate": 25, "store": 15}[self.value]


class TaskStatus(str, Enum):
    "任务状态。"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _format_transcript_for_note(transcript_data: dict[str, Any] | None, fallback_text: str) -> str:
    segments = transcript_data.get("segments", []) if transcript_data else []
    if not segments:
        return fallback_text

    lines: list[str] = []
    for segment in segments:
        start = timestamp_from_seconds(segment.get("start", 0))
        end = timestamp_from_seconds(segment.get("end", 0))
        text = str(segment.get("text", "")).strip()
        if text:
            lines.append(f"[{start} - {end}] {text}")

    return "\n".join(lines) or fallback_text


@dataclass
class StageResult:
    "单个阶段的执行结果。与文档 2.2 节接口定义一致。"
    success: bool
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineEvent:
    "流水线生命周期事件。与文档 2.2 节接口定义一致。"
    event: str       # progress / completed / error
    task_id: str
    video_id: str
    stage: str
    status: str      # running / completed / failed
    progress: int    # 0-100
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskCancelledError(Exception):
    "任务在执行过程中被取消时抛出。"
    pass


ProgressCallback = Callable[[PipelineEvent], None]


class PipelineTask:
    "单个流水线任务（队列中或运行中）。"

    def __init__(
        self,
        source_url: str,
        options: dict[str, Any] | None = None,
        task_id: str | None = None,
    ):
        self.task_id: str = task_id or f"task_{uuid.uuid4().hex[:12]}"
        self.source_url: str = source_url
        self.options: dict[str, Any] = options or {}
        self.status: TaskStatus = TaskStatus.PENDING
        self.current_stage: PipelineStage | None = None
        self.progress: int = 0
        self.error: str | None = None
        self.video_id: str | None = None
        self.video_db_id: int | None = None
        self.note_id: int | None = None
        self._created_at: float = time.time()
        self._cancelled: bool = False

    def cancel(self) -> None:
        self._cancelled = True
        self.status = TaskStatus.CANCELLED

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def created_at(self) -> float:
        return self._created_at


class PipelineOrchestrator:
    "编排视频处理流水线：任务队列、阶段调度、并发控制。"

    def __init__(
        self,
        transcriber: Transcriber | None = None,
        processor: Processor | None = None,
        video_processor: VideoProcessor | None = None,
        vector_store: VectorStore | None = None,
        llm: LLM | None = None,
        store: Store | None = None,
        retriever: Retriever | None = None,
        qa: QAEngine | None = None,
        max_concurrency: int = 2,
    ):
        self.processor = processor or MockProcessor()
        # VideoProcessor: 优先用真实 B 模块（BilibiliVideoProcessor）
        if video_processor:
            self.video_processor = video_processor
        else:
            try:
                from app.processor.video_processor import BilibiliVideoProcessor
                from app.core.config import settings
                self.video_processor = BilibiliVideoProcessor(data_dir=settings.data_dir)
            except Exception:
                self.video_processor = MockProcessor()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict[str, PipelineTask] = {}
        self._progress_callbacks: list[ProgressCallback] = []
        self._lock = asyncio.Lock()

        # ── LLM: 有 API key 则用真实客户端 ──
        if llm:
            self.llm = llm
        else:
            from app.core.config import settings
            if settings.tongyi_api_key or settings.deepseek_api_key:
                from app.llm.client import get_llm_client
                try:
                    self.llm = get_llm_client()
                except Exception:
                    self.llm = MockLLM()
            else:
                self.llm = MockLLM()

        # ── Transcriber: 配置了必剪凭证则用必剪 ──
        if transcriber:
            self.transcriber = transcriber
        else:
            from app.core.config import settings
            if settings.bjian_app_id and settings.bjian_access_token:
                self.transcriber = BjianTranscriber()
            else:
                try:
                    from app.transcriber.auto import AutoTranscriber
                    self.transcriber = AutoTranscriber()
                except Exception:
                    self.transcriber = MockTranscriber()

        # ── VectorStore: 暂时用 MockStore（ChromaDB 在 Python 3.13 下会崩溃） ──
        if vector_store:
            self.vector_store = vector_store
        else:
            try:
                from app.store.mock import MockStore
                self.vector_store = MockStore()
            except Exception:
                self.vector_store = MockStore()

        # ── Store: 配合 VectorStore 使用 ──
        self.store = store or MockStore()

        # ── Retriever: 有真实 VectorStore 则用 HybridRetriever ──
        if retriever:
            self.retriever = retriever
        elif not isinstance(self.vector_store, MockStore):
            from app.retriever.hybrid import HybridRetriever
            self.retriever = HybridRetriever(self.vector_store)
        else:
            self.retriever = MockRetriever(self.vector_store)

        # ── QAEngine: 有真实 Retriever 则用真实 QA ──
        if qa:
            self.qa = qa
        elif not isinstance(self.retriever, MockRetriever):
            from app.qa.engine import QAEngine
            self.qa = QAEngine(self.retriever)
        else:
            self.qa = MockQA(self.llm)

    async def start_task(self, source_url: str, options: dict[str, Any] | None = None) -> PipelineTask:
        "提交一个视频处理任务，立即返回。"
        client_task_id = str((options or {}).get("client_task_id") or "").strip()
        async with self._lock:
            existing = self._tasks.get(client_task_id)
            reusable_task_id = None
            if client_task_id.startswith("task_") and (
                existing is None
                or existing.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ):
                reusable_task_id = client_task_id

            task = PipelineTask(source_url, options, reusable_task_id)
            self._tasks[task.task_id] = task
        asyncio.create_task(self._run_task(task))
        return task

    def get_task(self, task_id: str) -> PipelineTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[PipelineTask]:
        return list(self._tasks.values())

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task.cancel()
            return True
        return False

    def on_progress(self, callback: ProgressCallback) -> None:
        "注册进度回调（用于 EventBus / WebSocket）。"
        self._progress_callbacks.append(callback)

    async def process_video(self, source_url: str) -> NoteResponse:
        "提交任务并等待完成。便利封装。"
        task = await self.start_task(source_url)
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            await asyncio.sleep(0.1)
        if task.status == TaskStatus.FAILED:
            raise RuntimeError(task.error)
        db = SessionLocal()
        try:
            note = db.query(Note).filter(Note.id == task.note_id).first() if task.note_id else None
            if not note and task.video_db_id:
                note = db.query(Note).filter(Note.video_id == task.video_db_id).first()
            if note:
                return NoteResponse.model_validate(note)
            raise RuntimeError("Note not found after processing")
        finally:
            db.close()

    async def answer_question(self, request: QARequest) -> QAResponse:
        "基于笔记内容回答问题。"
        context = await self.retriever.retrieve(request.question, request.note_id, request.top_k)
        answer = await self.qa.answer(request.question, context)
        return QAResponse(answer=answer, sources=context)

    def _resolve_task_llm(self, task: PipelineTask, db):
        "Resolve the LLM for a task, preferring the selected persisted provider/model."
        provider_id = str(task.options.get("provider_id") or "").strip()
        model_name = str(task.options.get("model_name") or "").strip()
        from app.llm.client import get_provider_llm_client
        from app.models.provider import EnabledModel, LLMProvider

        placeholder_ids = {"backend", "mock-backend", "mock-provider", "preview"}
        if provider_id in placeholder_ids or model_name in placeholder_ids:
            provider_id = ""
            model_name = ""

        if not provider_id and not model_name:
            enabled_model = (
                db.query(EnabledModel)
                .join(LLMProvider, EnabledModel.provider_id == LLMProvider.id)
                .filter(EnabledModel.enabled.is_(True), LLMProvider.enabled.is_(True))
                .order_by(EnabledModel.created_at.asc(), EnabledModel.id.asc())
                .first()
            )
            if enabled_model:
                provider = db.get(LLMProvider, enabled_model.provider_id)
                if provider and provider.api_key:
                    return get_provider_llm_client(provider, enabled_model.model_name)
            return self.llm

        if not provider_id or not model_name:
            raise RuntimeError("Provider 和模型名称必须同时提供")

        provider = db.get(LLMProvider, provider_id)
        if not provider:
            raise RuntimeError(f"Provider 不存在: {provider_id}")
        if not provider.enabled:
            raise RuntimeError(f"Provider 已禁用: {provider_id}")

        enabled_model = (
            db.query(EnabledModel)
            .filter(
                EnabledModel.provider_id == provider_id,
                EnabledModel.model_name == model_name,
            )
            .first()
        )
        if not enabled_model or not enabled_model.enabled:
            raise RuntimeError(f"模型未启用: {model_name}")

        return get_provider_llm_client(provider, model_name)

    async def _run_task(self, task: PipelineTask) -> None:
        "在并发控制下运行完整流水线。"
        async with self._semaphore:
            if task.cancelled:
                return
            db = SessionLocal()
            try:
                task.status = TaskStatus.RUNNING
                for stage in PipelineStage:
                    if task.cancelled:
                        return
                    await self._run_stage(task, stage, db)
                task.status = TaskStatus.COMPLETED
                self._emit(PipelineEvent(event="completed", task_id=task.task_id, video_id=task.video_id or "", stage="", status="completed", progress=100, message="处理完成"))
                db.commit()
            except TaskCancelledError:
                logger.warning(f"任务 {task.task_id} 被取消")
                pass
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.error = "任务被中断，可能是后端重载或进程退出"
                db.rollback()
                try:
                    if task.current_stage:
                        self._sync_task_model(task, task.current_stage, "failed", db)
                    db.commit()
                except Exception:
                    db.rollback()
                raise
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e) or f"{type(e).__name__}: {e!r}"
                stage_name = task.current_stage.label() if task.current_stage else "未知"
                logger.exception(f"任务 {task.task_id} 在阶段 [{stage_name}] 失败: {e}")
                db.rollback()
                try:
                    if task.video_id:
                        video = db.query(Video).filter(Video.video_id == task.video_id).first()
                        if video:
                            video.status = "failed"
                    if task.current_stage:
                        self._sync_task_model(task, task.current_stage, "failed", db)
                    db.commit()
                except Exception:
                    db.rollback()
                self._emit(PipelineEvent(event="error", task_id=task.task_id, video_id=task.video_id or "", stage=task.current_stage.value if task.current_stage else "", status="failed", progress=task.progress, message=task.error or str(e)))
            finally:
                db.close()

    async def _run_stage(self, task: PipelineTask, stage: PipelineStage, db) -> None:
        "执行单个流水线阶段。"
        task.current_stage = stage
        self._sync_task_model(task, stage, "running", db)
        self._emit(PipelineEvent(event="progress", task_id=task.task_id, video_id=task.video_id or "", stage=stage.value, status="running", progress=self._calc_progress(stage, 0), message=f"{stage.label()}..."))

        if stage == PipelineStage.PARSE:
            parse_result = await self.video_processor.parse(task.source_url, "")
            if not parse_result.success:
                raise RuntimeError(parse_result.error)

            meta = parse_result.metadata
            video_dir = parse_result.artifacts.get("video_dir", "")
            task.options["video_dir"] = video_dir

            video_id = meta.get("video_id", "")
            existing = db.query(Video).filter(Video.video_id == video_id).first()
            if existing:
                task.video_id = existing.video_id
                task.video_db_id = existing.id
            else:
                video = Video(
                    video_id=video_id,
                    url=task.source_url,
                    title=meta.get("title", task.source_url),
                    uploader=meta.get("uploader", ""),
                    uploader_uid=str(meta.get("uploader_uid", "")),
                    description=meta.get("description", ""),
                    duration_seconds=meta.get("duration_seconds"),
                    cover_url=meta.get("cover_url", ""),
                    bvid=meta.get("bvid"),
                    avid=meta.get("avid"),
                    status="pending",
                )
                db.add(video)
                db.flush()
                task.video_id = video.video_id
                task.video_db_id = video.id

        elif stage == PipelineStage.DOWNLOAD:
            video_dir = task.options.get("video_dir", "")
            if not video_dir:
                video_dir = str(project_path("data", "videos", task.video_id))

            def on_dl_progress(pct: float):
                self._sync_progress(task, stage, int(pct))

            dl_result = await self.video_processor.download(video_dir, quality=task.options.get("quality", "1080p"), progress_cb=on_dl_progress)
            if not dl_result.success:
                raise RuntimeError(dl_result.error)

            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.video_path = dl_result.artifacts.get("video_path")
                    video.file_size = dl_result.metadata.get("file_size")
                    video.status = "downloaded"
                    db.flush()

        elif stage == PipelineStage.TRANSCRIBE:
            video_dir = task.options.get("video_dir", "")
            if not video_dir:
                video_dir = str(project_path("data", "videos", task.video_id))

            # 先提取音频
            def on_audio_progress(pct: float):
                self._sync_progress(task, stage, int(pct * 0.3))

            audio_result = await self.video_processor.extract_audio(video_dir, on_audio_progress)
            if not audio_result.success:
                raise RuntimeError(audio_result.error or "音频提取失败，未返回错误详情")

            audio_path = audio_result.artifacts.get("audio_path", "")

            # 再转写
            def on_transcribe_progress(pct: float):
                self._sync_progress(task, stage, 30 + int(pct * 0.7))

            transcribe_result = await self.transcriber.transcribe(audio_path, video_dir, on_transcribe_progress)
            if not transcribe_result.success:
                raise RuntimeError(transcribe_result.error or "语音转写失败，未返回错误详情")

            # 保存转写结果到 task.options，供 GENERATE 阶段使用
            full_text = transcribe_result.metadata.get("full_text", "")
            task.options["transcript_text"] = full_text

            # 读取 transcription.json 中的分段数据，供前端展示
            import json
            from pathlib import Path as _Path
            trans_json_path = transcribe_result.artifacts.get("transcript_json", "")
            if trans_json_path:
                try:
                    tj_data = json.loads(_Path(trans_json_path).read_text(encoding="utf-8"))
                    segments = tj_data.get("segments", [])
                    language = tj_data.get("language", "zh-CN")
                    task.options["transcript_data"] = {
                        "full_text": full_text,
                        "language": language,
                        "raw": None,
                        "segments": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments],
                    }
                except Exception:
                    pass

            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.audio_path = str(audio_path)
                    video.status = "transcribed"
                    db.flush()

        elif stage == PipelineStage.GENERATE:
            self._sync_progress(task, stage, 10)
            notes_dir = project_path("data", "notes")
            notes_dir.mkdir(parents=True, exist_ok=True)
            note_file = notes_dir / f"{task.video_id or task.task_id}.md"

            # 用 NoteGenerator 生成笔记（使用 TRANSCRIBE 阶段的实际转写文本）
            transcript_text = task.options.get("transcript_text", "")
            if not transcript_text:
                transcript_text = "这是模拟转录文本。"
            transcript_for_note = _format_transcript_for_note(
                task.options.get("transcript_data"),
                transcript_text,
            )
            video_meta = {
                "title": task.video_id or task.task_id,
                "uploader": "",
                "duration_seconds": 0,
            }
            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video_meta = {
                        "title": video.title or task.video_id,
                        "uploader": video.uploader or "",
                        "duration_seconds": video.duration_seconds or 0,
                    }

            from app.note.generator import NoteGenerator
            task_llm = self._resolve_task_llm(task, db)
            note_gen = NoteGenerator(llm=task_llm)
            note_result = await note_gen.generate(
                transcript_for_note,
                video_meta,
            )
            note_content = note_result.get("markdown_content", transcript_text)
            note_file.write_text(note_content, encoding="utf-8")
            self._sync_progress(task, stage, 60)
            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.status = "generating"
                    # 删除已有笔记（支持重新生成）
                    old_note = db.query(Note).filter(Note.video_id == video.id).first()
                    if old_note:
                        db.query(Chunk).filter(Chunk.note_id == old_note.id).delete()
                        db.delete(old_note)
                        db.flush()
                    note = Note(
                        video_id=video.id,
                        file_path=str(note_file),
                        summary=note_result.get("summary", ""),
                        keywords=str(note_result.get("keywords", [])),
                        total_chunks=0,
                        section_count=len(note_result.get("sections", [])),
                        char_count=len(note_content),
                        model_used="NoteGenerator",
                    )
                    db.add(note)
                    db.flush()
                    task.note_id = note.id
                    self._sync_progress(task, stage, 80)

        elif stage == PipelineStage.STORE:
            self._sync_progress(task, stage, 10)
            if task.note_id and self.vector_store:
                db_note = db.query(Note).filter(Note.id == task.note_id).first()
                if db_note and db_note.file_path:
                    note_path = Path(db_note.file_path)
                    if note_path.exists():
                        note_content = note_path.read_text(encoding="utf-8")
                        video_title = task.video_id or ""
                        if task.video_id:
                            v = db.query(Video).filter(Video.video_id == task.video_id).first()
                            if v:
                                video_title = v.title
                        self._sync_progress(task, stage, 40)
                        try:
                            chunk_count = await self.vector_store.store_note(
                                task.video_id or task.task_id,
                                note_content,
                                video_title,
                            )
                            db_note.total_chunks = chunk_count or 0
                            db.flush()
                        except Exception as e:
                            task.error = f"向量索引失败: {e}"
                            raise RuntimeError(f"向量索引失败: {e}")
                    else:
                        task.error = f"笔记文件不存在: {note_path}"
                        raise RuntimeError(f"笔记文件不存在: {note_path}")
            if task.video_id:
                v = db.query(Video).filter(Video.video_id == task.video_id).first()
                if v:
                    v.status = "stored"
                    db.flush()
            self._sync_progress(task, stage, 100)

        self._sync_task_model(task, stage, "completed", db)
        db.commit()

    def _calc_progress(self, stage: PipelineStage, stage_progress: int) -> int:
        "计算总体进度百分比。"
        stages = list(PipelineStage)
        base = sum(s.progress_weight() for s in stages[:stages.index(stage)])
        return base + int(stage.progress_weight() * stage_progress / 100)

    def _sync_progress(self, task: PipelineTask, stage: PipelineStage, pct: int) -> None:
        "更新进度并发送事件。"
        task.progress = self._calc_progress(stage, pct)
        self._emit(PipelineEvent(event="progress", task_id=task.task_id, video_id=task.video_id or "", stage=stage.value, status="running", progress=task.progress, message=f"{stage.label()} ({pct}%)"))

    def _sync_task_model(self, task: PipelineTask, stage: PipelineStage, status: str, db) -> None:
        "同步任务状态到数据库 Task 模型。"
        try:
            if not task.video_id:
                return
            tid = f"{task.task_id}_{stage.value}"
            t = db.query(TaskModel).filter(TaskModel.task_id == tid, TaskModel.type == stage.value).first()
            progress = task.progress if status == "running" else 100
            error_message = task.error if status == "failed" else None
            if not t:
                t = TaskModel(
                    task_id=tid,
                    video_id=task.video_db_id or task.note_id or 0,
                    type=stage.value,
                    status=status,
                    progress=progress,
                    error_message=error_message,
                )
                db.add(t)
            else:
                t.status = status
                t.progress = progress
                if status == "running" and not t.started_at:
                    t.started_at = datetime.utcnow()
                elif status == "completed":
                    t.completed_at = datetime.utcnow()
                elif status == "failed":
                    t.error_message = error_message
            db.flush()
        except Exception as e:
            logger.error(f"同步任务模型失败 ({task.task_id}_{stage.value}): {e}")

    def _emit(self, event: PipelineEvent) -> None:
        "将事件分发到所有已注册的回调。"
        for cb in self._progress_callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"事件回调异常 ({event.event}/{event.task_id}): {e}")
