"""
处理器协议。

- VideoProcessor: 视频下载、音频提取（角色 B）
- Processor: 转录文本拆分为结构化文本块（角色 C 向量化前处理）
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.schemas.chunk import ChunkBase
from app.schemas.stage import StageResult
from app.schemas.transcript import TranscriptResult


class VideoProcessor(Protocol):
    """视频下载与音频提取接口（按团队分工文档 角色 B 3.2 节定义）。"""

    async def parse(self, url: str, video_dir: str) -> StageResult:
        """解析视频链接，提取元数据。

        Args:
            url: 视频链接（B 站 BV/AV/短链接）
            video_dir: 产物目录，解析结果写入 meta.json

        Returns:
            StageResult: .artifacts["meta_json"] 为 meta.json 路径
                         .metadata 含 video_id, title, uploader 等字段
        """
        ...

    async def download(
        self,
        video_dir: str,
        quality: str = "1080p",
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """下载视频文件。

        Args:
            video_dir: 产物目录（从中读取 meta.json 获取 URL）
            quality: 画质选择（360p/480p/720p/1080p）
            progress_cb: 可选进度回调，接收 0.0-100.0

        Returns:
            StageResult: .artifacts["video_path"] 为视频文件路径
        """
        ...

    async def extract_audio(
        self,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """从视频中提取音频（16kHz, mono, WAV）。

        Args:
            video_dir: 产物目录（从中读取 video.mp4）
            progress_cb: 可选进度回调，接收 0.0-100.0

        Returns:
            StageResult: .artifacts["audio_path"] 为音频文件路径
        """
        ...


class Processor(Protocol):
    """对转录结果进行拆分、清洗、丰富，生成结构化文本块。"""

    async def process(
        self, transcript: TranscriptResult, note_id: int, video_id: str
    ) -> list[ChunkBase]:
        ...
