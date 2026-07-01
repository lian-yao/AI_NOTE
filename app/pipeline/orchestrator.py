"Pipeline orchestrator: task queue, concurrency control, stage orchestration."

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from app.core.database import SessionLocal
from app.core.paths import project_path
from app.models.video import Video
from app.models.note import Note
from app.models.task import Task as TaskModel
from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse

from app.transcriber import Transcriber
from app.processor import Processor
from app.llm import LLM
from app.store import Store
from app.retriever import Retriever
from app.qa import QAEngine

from app.transcriber.mock import MockTranscriber
from app.processor.mock import MockProcessor
from app.llm.mock import MockLLM
from app.store.mock import MockStore
from app.retriever.mock import MockRetriever
from app.qa.mock import MockQA


class PipelineStage(str, Enum):
    "Pipeline processing stages."
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
    "Pipeline task status."
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StageResult:
    "Single stage execution result. Matches doc section 2.2."
    success: bool
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineEvent:
    "Pipeline lifecycle event. Matches doc section 2.2."
    event: str       # progress / completed / error
    task_id: str
    video_id: str
    stage: str
    status: str      # running / completed / failed
    progress: int    # 0-100
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskCancelledError(Exception):
    "Raised when a task is cancelled during execution."
    pass


ProgressCallback = Callable[[PipelineEvent], None]


class PipelineTask:
    "A single pipeline task (in queue or running)."

    def __init__(self, source_url: str, options: dict[str, Any] | None = None):
        self.task_id: str = f"task_{uuid.uuid4().hex[:12]}"
        self.source_url: str = source_url
        self.options: dict[str, Any] = options or {}
        self.status: TaskStatus = TaskStatus.PENDING
        self.current_stage: PipelineStage | None = None
        self.progress: int = 0
        self.error: str | None = None
        self.video_id: str | None = None
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
    "Orchestrates video processing pipeline: task queue, stages, concurrency."

    def __init__(
        self,
        transcriber: Transcriber | None = None,
        processor: Processor | None = None,
        llm: LLM | None = None,
        store: Store | None = None,
        retriever: Retriever | None = None,
        qa: QAEngine | None = None,
        max_concurrency: int = 2,
    ):
        self.transcriber = transcriber or MockTranscriber()
        self.processor = processor or MockProcessor()
        self.llm = llm or MockLLM()
        self.store = store or MockStore()
        self.retriever = retriever or MockRetriever(self.store)
        self.qa = qa or MockQA(self.llm)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict[str, PipelineTask] = {}
        self._progress_callbacks: list[ProgressCallback] = []
        self._lock = asyncio.Lock()

    async def start_task(self, source_url: str, options: dict[str, Any] | None = None) -> PipelineTask:
        "Submit a video processing task. Returns immediately."
        task = PipelineTask(source_url, options)
        async with self._lock:
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
        "Register a progress callback (for EventBus / WebSocket)."
        self._progress_callbacks.append(callback)

    async def process_video(self, source_url: str) -> NoteResponse:
        "Submit task and wait for completion. Convenience wrapper."
        task = await self.start_task(source_url)
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            await asyncio.sleep(0.1)
        if task.status == TaskStatus.FAILED:
            raise RuntimeError(task.error)
        db = SessionLocal()
        try:
            note = db.query(Note).filter(Note.video_id == task.note_id).first()
            if note:
                return NoteResponse.model_validate(note)
            raise RuntimeError("Note not found after processing")
        finally:
            db.close()

    async def answer_question(self, request: QARequest) -> QAResponse:
        "Answer a question based on note content."
        context = await self.retriever.retrieve(request.question, request.note_id, request.top_k)
        answer = await self.qa.answer(request.question, context)
        return QAResponse(answer=answer, sources=context)

    async def _run_task(self, task: PipelineTask) -> None:
        "Run the full pipeline with concurrency control."
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
            except TaskCancelledError:
                pass
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self._emit(PipelineEvent(event="error", task_id=task.task_id, video_id=task.video_id or "", stage=task.current_stage.value if task.current_stage else "", status="failed", progress=task.progress, message=str(e)))
            finally:
                db.close()

    async def _run_stage(self, task: PipelineTask, stage: PipelineStage, db) -> None:
        "Execute a single pipeline stage."
        task.current_stage = stage
        self._sync_task_model(task, stage, "running", db)
        self._emit(PipelineEvent(event="progress", task_id=task.task_id, video_id=task.video_id or "", stage=stage.value, status="running", progress=self._calc_progress(stage, 0), message=f"{stage.label()}..."))

        if stage == PipelineStage.PARSE:
            import time as tm
            video = Video(video_id=f"b_{int(tm.time())}", url=task.source_url, title=task.source_url, status="pending")
            db.add(video)
            db.flush()
            task.video_id = video.video_id
            task.note_id = video.id

        elif stage == PipelineStage.DOWNLOAD:
            self._sync_progress(task, stage, 50)
            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.status = "downloading"
                    db.flush()

        elif stage == PipelineStage.TRANSCRIBE:
            self._sync_progress(task, stage, 20)
            audio_path = project_path("data", "mock_audio.mp3")
            transcript = await self.transcriber.transcribe(audio_path)
            self._sync_progress(task, stage, 80)
            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.status = "transcribing"
                    video.audio_path = str(audio_path)
                    db.flush()

        elif stage == PipelineStage.GENERATE:
            self._sync_progress(task, stage, 10)
            notes_dir = project_path("data", "notes")
            notes_dir.mkdir(parents=True, exist_ok=True)
            note_file = notes_dir / f"{task.video_id or task.task_id}.md"
            note_content = await self.llm.chat([
                {"role": "system", "content": "根据以下转录文本生成结构化笔记："},
                {"role": "user", "content": "这是模拟转录文本。"},
            ])
            note_file.write_text(note_content, encoding="utf-8")
            self._sync_progress(task, stage, 60)
            if task.video_id:
                video = db.query(Video).filter(Video.video_id == task.video_id).first()
                if video:
                    video.status = "generating"
                    note = Note(video_id=video.id, file_path=str(note_file), summary="笔记摘要(Mock)", keywords='["AI"]', total_chunks=0, section_count=1, char_count=len(note_content), model_used="mock")
                    db.add(note)
                    db.flush()
                    task.note_id = note.id
                    self._sync_progress(task, stage, 80)
                    from app.schemas.transcript import TranscriptResult
                    chunks = await self.processor.process(TranscriptResult(segments=[], full_text=note_content, language="zh"), note.id, task.video_id)
                    await self.store.add_chunks(chunks)
                    self._sync_progress(task, stage, 100)

        elif stage == PipelineStage.STORE:
            self._sync_progress(task, stage, 100)

        self._sync_task_model(task, stage, "completed", db)

    def _calc_progress(self, stage: PipelineStage, stage_progress: int) -> int:
        "Calculate overall progress percentage."
        stages = list(PipelineStage)
        base = sum(s.progress_weight() for s in stages[:stages.index(stage)])
        return base + int(stage.progress_weight() * stage_progress / 100)

    def _sync_progress(self, task: PipelineTask, stage: PipelineStage, pct: int) -> None:
        "Update progress and emit event."
        task.progress = self._calc_progress(stage, pct)
        self._emit(PipelineEvent(event="progress", task_id=task.task_id, video_id=task.video_id or "", stage=stage.value, status="running", progress=task.progress, message=f"{stage.label()} ({pct}%)"))

    def _sync_task_model(self, task: PipelineTask, stage: PipelineStage, status: str, db) -> None:
        "Sync task state to database Task model."
        try:
            if not task.video_id:
                return
            t = db.query(TaskModel).filter(TaskModel.task_id == task.task_id, TaskModel.type == stage.value).first()
            if not t:
                t = TaskModel(task_id=task.task_id, video_id=task.note_id or 0, type=stage.value, status=status, progress=0 if status == "running" else 100)
                db.add(t)
            else:
                t.status = status
                t.progress = task.progress if status == "running" else 100
                if status == "running" and not t.started_at:
                    t.started_at = datetime.utcnow()
                elif status == "completed":
                    t.completed_at = datetime.utcnow()
                elif status == "failed":
                    t.error_message = task.error
            db.flush()
        except Exception:
            pass

    def _emit(self, event: PipelineEvent) -> None:
        "Dispatch event to all registered callbacks."
        for cb in self._progress_callbacks:
            try:
                cb(event)
            except Exception:
                pass
