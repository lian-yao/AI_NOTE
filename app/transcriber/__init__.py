"""
转写器协议：将音频/视频转录为结构化文本。

按团队分工文档（角色 B 3.2 节）定义接口签名。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.schemas.stage import StageResult


class Transcriber(Protocol):
    """音频/视频文件转写接口（策略模式抽象基类）。"""

    async def transcribe(
        self,
        audio_path: str,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """转写音频文件。

        Args:
            audio_path: 音频文件路径（16kHz mono WAV）
            video_dir: 视频产物目录，用于存放 transcription.json / .srt
            progress_cb: 可选进度回调，接收 0.0-100.0 的进度百分比

        Returns:
            StageResult: .artifacts["transcript_json"] 为转写 JSON 路径
                         .artifacts["transcript_srt"] 为 SRT 字幕路径
        """
        ...
