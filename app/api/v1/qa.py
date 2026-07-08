"""QA API?????? + ??????"""
import asyncio
import json
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.model_usage import get_configured_llm_client
from app.schemas.qa import QARequest, QAResponse
from app.schemas.chunk import ChunkBase, SearchResult
from app.qa.mock import MockQA
from app.qa.engine import QAEngine


class GlobalQARequest(BaseModel):
    question: str
    top_k: int = 5
    video_ids: list[str] | None = None


class IndexRequest(BaseModel):
    task_id: str | None = None
    video_id: str | None = None


router = APIRouter(prefix="/qa", tags=["qa"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


def _resolve_request_llm(body: QARequest, db: Session):
    try:
        return get_configured_llm_client(
            db,
            purpose="qa",
            provider_id=body.provider_id,
            model_name=body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _source_to_search_result(src) -> SearchResult:
    if hasattr(src, "chunk"):
        return src

    meta = src.get("metadata", {}) if isinstance(src, dict) else {}
    text = src.get("document") or src.get("content", "") if isinstance(src, dict) else ""
    distance = src.get("distance", 0) if isinstance(src, dict) else 0

    return SearchResult(
        chunk=ChunkBase(
            chunk_id=src.get("id", "") if isinstance(src, dict) else "",
            video_id=0,
            note_id=hash(meta.get("video_id", "")) % 10000,
            chunk_index=meta.get("chunk_index", 0),
            section_title=meta.get("section_title"),
            content=text,
            start_time=meta.get("start_time"),
            end_time=meta.get("end_time"),
        ),
        score=1.0 - distance,
    )


def _is_generated_reference_footer(token: str) -> bool:
    stripped = token.lstrip()
    return stripped.startswith("---") and "引用来源" in stripped


def _resolve_video(db: Session, video_id: str | None = None, task_id: str | None = None):
    from app.models.task import Task
    from app.models.video import Video

    video_key = (video_id or "").strip()
    if video_key:
        video = db.query(Video).filter(Video.video_id == video_key).first()
        if video:
            return video

    task_key = (task_id or "").strip()
    if not task_key:
        return None

    task = db.query(Task).filter(Task.task_id == task_key).first()
    if not task:
        task = (
            db.query(Task)
            .filter(Task.task_id.like(f"{task_key}_%"))
            .order_by(Task.created_at.desc())
            .first()
        )
    if task:
        return task.video

    return db.query(Video).filter(Video.video_id == task_key).first()


def _index_status_payload(db: Session, video_id: str | None = None, task_id: str | None = None) -> dict:
    from app.models.chunk import Chunk
    from app.models.note import Note

    video = _resolve_video(db, video_id=video_id, task_id=task_id)
    if video:
        chunk_count = db.query(Chunk).filter(Chunk.video_id == video.id).count()
        if chunk_count > 0:
            return {"indexed": True, "status": "indexed", "chunks": chunk_count, "video_id": video.video_id}
        note = db.query(Note).filter(Note.video_id == video.id).first()
        if note:
            return {"indexed": False, "status": "idle", "chunks": 0, "video_id": video.video_id}
        return {
            "indexed": False,
            "status": "failed",
            "chunks": 0,
            "video_id": video.video_id,
            "error": "未找到可索引的笔记",
        }

    total_chunks = db.query(Chunk).count()
    return {"indexed": total_chunks > 0, "status": "indexed" if total_chunks > 0 else "idle", "chunks": total_chunks}


async def _rebuild_note_index(db: Session, video, orchestrator) -> dict:
    from pathlib import Path

    from app.core.logger import logger
    from app.models.chunk import Chunk
    from app.models.note import Note
    from app.store.chunker import semantic_chunk
    from app.store.embedder import EmbeddingConfigurationError

    note = db.query(Note).filter(Note.video_id == video.id).first()
    if not note:
        raise HTTPException(404, "未找到可索引的笔记")

    note_path = Path(note.file_path)
    if not note_path.exists():
        raise HTTPException(404, f"笔记文件不存在: {note_path}")

    note_content = note_path.read_text(encoding="utf-8")
    chunks = semantic_chunk(note_content)
    db.query(Chunk).filter(Chunk.note_id == note.id).delete()

    keyword_items = []
    for idx, chunk in enumerate(chunks):
        chunk_id = f"{video.video_id}_{idx}"
        content = chunk.get("content", "")
        db.add(Chunk(
            chunk_id=chunk_id,
            video_id=video.id,
            note_id=note.id,
            chunk_index=idx,
            section_title=chunk.get("title"),
            content=content,
            start_time=chunk.get("start_time", 0),
            end_time=chunk.get("end_time", 0),
            chroma_id=chunk_id,
            token_count=len(content),
        ))
        keyword_items.append({
            "id": chunk_id,
            "document": content,
            "metadata": {
                "video_id": video.video_id,
                "video_title": video.title,
                "section_title": chunk.get("title"),
                "chunk_index": idx,
                "start_time": chunk.get("start_time", 0),
                "end_time": chunk.get("end_time", 0),
            },
        })

    note.total_chunks = len(chunks)
    db.flush()

    retriever = getattr(orchestrator, "retriever", None)
    if keyword_items and hasattr(retriever, "build_keyword_index"):
        retriever.build_keyword_index(keyword_items)

    vector_indexed = False
    vector_error = None
    vector_store = getattr(orchestrator, "vector_store", None)
    if vector_store and chunks:
        try:
            await vector_store.delete_vectors(video.video_id)
            await vector_store.store_note(video.video_id, note_content, video.title)
            vector_indexed = True
        except EmbeddingConfigurationError as exc:
            vector_error = str(exc)
            logger.warning(f"Embedding 未配置，已仅重建关键词索引: {exc}")
        except Exception as exc:
            vector_error = str(exc)[:200]
            logger.warning(f"向量索引重建失败，已保留关键词索引: {exc}")

    db.commit()
    return {
        "indexed": len(chunks) > 0,
        "status": "indexed" if chunks else "idle",
        "chunks": len(chunks),
        "video_id": video.video_id,
        "vector_indexed": vector_indexed,
        "vector_error": vector_error,
    }


@router.post("/ask", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    orchestrator=Depends(get_orchestrator),
    db: Session = Depends(get_db),
):
    """??????"""
    qa = orchestrator.qa
    retriever = orchestrator.retriever
    sources = await retriever.retrieve(body.question, top_k=body.top_k, note_id=body.note_id)
    llm = _resolve_request_llm(body, db)

    if isinstance(qa, QAEngine):
        answer_parts = []
        skip_reference_tokens = False
        async for token in qa.ask(
            body.question,
            mode="single" if body.note_id else "global",
            video_id=body.note_id,
            top_k=body.top_k,
            llm=llm,
            history=body.history,
        ):
            if _is_generated_reference_footer(token):
                skip_reference_tokens = True
                continue
            if not skip_reference_tokens:
                answer_parts.append(token)
        answer = "".join(answer_parts)
    else:
        answer = await qa.answer(body.question, [src for src in sources])

    return QAResponse(answer=answer, sources=[_source_to_search_result(src) for src in sources])


@router.post("/ask/stream")
async def ask_question_stream(
    body: QARequest,
    orchestrator=Depends(get_orchestrator),
    db: Session = Depends(get_db),
):
    """??????? SSE ????"""
    async def event_generator():
        qa = orchestrator.qa
        retriever = orchestrator.retriever

        try:
            llm = _resolve_request_llm(body, db)
            sources = await retriever.retrieve(body.question, top_k=body.top_k, note_id=body.note_id)
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'问答请求失败：{str(exc)[:200]}'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        # ??????
        try:
            if isinstance(qa, QAEngine):
                skip_reference_tokens = False
                async for token in qa.ask(
                    body.question,
                    mode="single" if body.note_id else "global",
                    video_id=body.note_id,
                    top_k=body.top_k,
                    llm=llm,
                    history=body.history,
                ):
                    if _is_generated_reference_footer(token):
                        skip_reference_tokens = True
                        continue
                    if not skip_reference_tokens:
                        yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                answer = await qa.answer(body.question, [src for src in sources])
                for char in answer:
                    yield f"data: {json.dumps({'token': char})}\n\n"
                    await asyncio.sleep(0.01)
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'问答生成失败：{str(exc)[:200]}'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        # ?? sources
        source_list = []
        for src in sources:
            if hasattr(src, 'chunk'):
                chunk = src.chunk
                text = getattr(chunk, 'content', '')
                section_title = getattr(chunk, 'section_title', '')
                start_time = getattr(chunk, 'start_time', None)
                end_time = getattr(chunk, 'end_time', None)
            elif isinstance(src, dict):
                meta = src.get('metadata', {})
                text = src.get('document') or src.get('content', '')
                section_title = meta.get('section_title', '')
                start_time = meta.get('start_time')
                end_time = meta.get('end_time')
            else:
                text = ''
                section_title = ''
                start_time = None
                end_time = None
            source_list.append({
                'text': text,
                'section_title': section_title,
                'start_time': start_time,
                'end_time': end_time,
            })
        yield f"data: {json.dumps({'sources': source_list})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/ask-global", response_model=QAResponse)
async def ask_global_question(body: GlobalQARequest, orchestrator=Depends(get_orchestrator)):
    """?????????"""
    qa_req = QARequest(
        question=body.question,
        note_id=None,
        top_k=body.top_k,
    )
    return await orchestrator.answer_question(qa_req)


@router.get("/index/status")
def get_index_status(
    task_id: str | None = None,
    video_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Check QA index status for the current note."""
    return _index_status_payload(db, video_id=video_id, task_id=task_id)


@router.post("/index")
async def rebuild_index(
    body: IndexRequest,
    orchestrator=Depends(get_orchestrator),
    db: Session = Depends(get_db),
):
    """Rebuild SQL keyword chunks and best-effort vector index for a note."""
    video = _resolve_video(db, video_id=body.video_id, task_id=body.task_id)
    if not video:
        raise HTTPException(404, "未找到对应视频")
    try:
        return await _rebuild_note_index(db, video, orchestrator)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"重建索引失败：{str(exc)[:200]}") from exc
