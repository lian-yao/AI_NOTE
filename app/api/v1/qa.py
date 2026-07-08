"""QA API?????? + ??????"""
import asyncio
import json
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.schemas.qa import QARequest, QAResponse
from app.qa.mock import MockQA
from app.qa.engine import QAEngine


class GlobalQARequest(BaseModel):
    question: str
    top_k: int = 5
    video_ids: list[str] | None = None


router = APIRouter(prefix="/qa", tags=["qa"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/ask", response_model=QAResponse)
async def ask_question(body: QARequest, orchestrator=Depends(get_orchestrator)):
    """??????"""
    return await orchestrator.answer_question(body)


@router.post("/ask/stream")
async def ask_question_stream(body: QARequest, orchestrator=Depends(get_orchestrator)):
    """??????? SSE ????"""
    async def event_generator():
        qa = orchestrator.qa
        retriever = orchestrator.retriever

        # ????? sources
        sources = await retriever.retrieve(body.question, top_k=body.top_k, note_id=body.note_id)

        # ??????
        if isinstance(qa, QAEngine):
            async for token in qa.ask(body.question, video_id=body.note_id, top_k=body.top_k):
                if not token.startswith("\n\n---"):
                    yield f"data: {json.dumps({'token': token})}\n\n"
        else:
            answer = await qa.answer(body.question, [src for src in sources])
            for char in answer:
                yield f"data: {json.dumps({'token': char})}\n\n"
                await asyncio.sleep(0.01)

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
def get_index_status():
    """Check QA vector index status."""
    from app.store.vector import VectorStore
    try:
        vs = VectorStore()
        count = vs.collection.count()
        return {"status": "ready" if count > 0 else "empty", "chunks": count}
    except Exception as e:
        return {"status": "error", "chunks": 0, "error": str(e)[:100]}
