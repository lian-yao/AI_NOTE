"""
Mock 处理实现（含 VideoProcessor 方法 + 原有的文本分块方法）。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.schemas.chunk import ChunkBase
from app.schemas.stage import StageResult
from app.schemas.transcript import TranscriptResult


class MockProcessor:
    """Mock 处理器：同时提供 VideoProcessor 和 chunk 处理能力。"""

    # ========== VideoProcessor 方法 ==========

    async def parse(self, url: str, video_dir: str) -> StageResult:
        """Mock 链接解析。"""
        return StageResult(
            success=True,
            artifacts={"meta_json": str(Path(video_dir) / "meta.json")},
            metadata={
                "video_id": "b_mock123",
                "title": "Mock 视频标题",
                "uploader": "Mock UP 主",
                "duration_seconds": 1800,
                "bvid": "mock123",
                "avid": None,
            },
        )

    async def download(
        self,
        video_dir: str,
        quality: str = "1080p",
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """Mock 视频下载。"""
        if progress_cb:
            progress_cb(100.0)
        return StageResult(
            success=True,
            artifacts={"video_path": str(Path(video_dir) / "video.mp4")},
            metadata={"quality": quality},
        )

    async def extract_audio(
        self,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """Mock 音频提取。"""
        if progress_cb:
            progress_cb(100.0)
        return StageResult(
            success=True,
            artifacts={"audio_path": str(Path(video_dir) / "audio.wav")},
            metadata={"audio_duration_seconds": 1800, "sample_rate": 16000},
        )

    # ========== 文本分块方法 ==========

    async def process(
        self, transcript: TranscriptResult, note_id: int, video_id: str
    ) -> list[ChunkBase]:
        return [
            ChunkBase(
                chunk_id=f"{video_id}_{i}",
                video_id=0,
                note_id=note_id,
                content=seg.text,
                chunk_index=i,
                section_title=f"章节 {i + 1}",
                start_time=seg.start,
                end_time=seg.end,
            )
            for i, seg in enumerate(transcript.segments)
        ]
