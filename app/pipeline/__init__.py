"""
Pipeline protocol: orchestrate the full video processing workflow.
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse


class Pipeline(Protocol):
    """Full workflow orchestration."""

    async def process_video(self, source_url: str) -> NoteResponse:
        ...

    async def answer_question(self, request: QARequest) -> QAResponse:
        ...
