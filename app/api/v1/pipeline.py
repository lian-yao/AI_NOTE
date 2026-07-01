"""
Pipeline API 端点。
"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request

from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse


class GlobalQARequest(BaseModel):
    question: str
    top_k: int = 5
    video_ids: list[str] | None = None


class ProcessRequest(BaseModel):
    source_url: str


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/process", response_model=NoteResponse)
async def process_video(body: ProcessRequest, orchestrator=Depends(get_orchestrator)):
    """处理 B 站视频：下载 -> 转写 -> 生成笔记。"""
    return await orchestrator.process_video(body.source_url)


@router.post("/ask", response_model=QAResponse)
async def ask_question(request: QARequest, orchestrator=Depends(get_orchestrator)):
    """基于笔记内容回答问题。"""
    return await orchestrator.answer_question(request)
