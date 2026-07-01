"""
Pipeline protocol: orchestrate video processing workflow.
"""
from __future__ import annotations

from app.pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineTask,
    PipelineEvent,
    PipelineStage,
    TaskStatus,
    StageResult,
    ProgressCallback,
)
from app.pipeline.events import EventBus

__all__ = [
    "PipelineOrchestrator",
    "PipelineTask",
    "PipelineEvent",
    "PipelineStage",
    "TaskStatus",
    "StageResult",
    "ProgressCallback",
    "EventBus",
]
