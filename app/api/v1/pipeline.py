"""
Pipeline API 端点。
"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request

from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse


class ProcessRequest(BaseModel):
    source_url: str


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_pipeline(request: Request):
    return request.app.state.pipeline


@router.post("/process", response_model=NoteResponse)
async def process_video(body: ProcessRequest, pipeline=Depends(get_pipeline)):
    """处理 B 站视频：下载 -> 转写 -> 生成笔记。"""
    return await pipeline.process_video(body.source_url)


@router.post("/ask", response_model=QAResponse)
async def ask_question(request: QARequest, pipeline=Depends(get_pipeline)):
    """基于笔记内容回答问题。"""
    return await pipeline.answer_question(request)
