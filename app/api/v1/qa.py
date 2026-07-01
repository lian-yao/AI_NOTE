"""QA API：单视频问答 + 跨视频问答。"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request

from app.schemas.qa import QARequest, QAResponse


class GlobalQARequest(BaseModel):
    question: str
    top_k: int = 5
    video_ids: list[str] | None = None


router = APIRouter(prefix="/qa", tags=["qa"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/ask", response_model=QAResponse)
async def ask_question(body: QARequest, orchestrator=Depends(get_orchestrator)):
    """单视频问答。"""
    return await orchestrator.answer_question(body)


@router.post("/ask-global", response_model=QAResponse)
async def ask_global_question(body: GlobalQARequest, orchestrator=Depends(get_orchestrator)):
    """跨视频知识库问答。"""
    qa_req = QARequest(
        question=body.question,
        note_id=None,
        top_k=body.top_k,
    )
    return await orchestrator.answer_question(qa_req)
