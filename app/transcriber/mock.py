"""
Mock 转写实现（匹配新 Transcriber 协议签名）。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.schemas.stage import StageResult


class MockTranscriber:
    """返回固定示例文本的 Mock 转写器。"""

    async def transcribe(
        self,
        audio_path: str,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        # 模拟进度
        if progress_cb:
            progress_cb(50.0)
            progress_cb(100.0)

        return StageResult(
            success=True,
            artifacts={
                "transcript_json": str(Path(video_dir) / "transcription.json"),
                "transcript_srt": str(Path(video_dir) / "transcription.srt"),
            },
            metadata={
                "full_text": "人工智能正在改变世界。深度学习让计算机能够理解图像和语言。未来十年将有更多突破性进展。",
                "language": "zh",
                "segment_count": 3,
                "duration_seconds": 7.0,
                "model_size": "mock",
            },
        )
