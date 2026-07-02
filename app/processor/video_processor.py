"""Bilibili 视频处理器适配器。
将 B 模块的独立函数（parser/downloader/audio）包装为 VideoProcessor Protocol 接口。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.processor.storage import ensure_video_dir
from app.schemas.stage import StageResult


class BilibiliVideoProcessor:
    """Bilibili 视频处理器。

    包装 B 模块的独立函数，实现 VideoProcessor Protocol 约定的类方法签名，
    供 PipelineOrchestrator 调用。
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir

    async def parse(self, url: str, video_dir: str = "") -> StageResult:
        """解析 B 站视频链接并提取元数据。

        Args:
            url: B 站视频链接（BV/AV/短链接）
            video_dir: 忽略，由内部根据 data_dir + video_id 决定产物目录

        Returns:
            StageResult:
                - .metadata 包含 video_id, title, uploader 等
                - .artifacts["video_dir"] 为实际产物目录路径
        """
        if video_dir:
            return await self._parse_with_dir(url, video_dir)

        from app.processor.parser import parse_bilibili_url
        result = await parse_bilibili_url(url, self.data_dir)
        if result.success:
            video_id = result.metadata.get("video_id", "")
            actual_dir = str(ensure_video_dir(video_id, self.data_dir))
            result.artifacts["video_dir"] = actual_dir
            result.metadata["video_dir"] = actual_dir
        return result

    async def _parse_with_dir(self, url: str, video_dir: str) -> StageResult:
        from app.processor.parser import _extract_bvid, _extract_avid, _build_video_id
        from app.processor.storage import save_meta_json

        bvid = _extract_bvid(url)
        avid = _extract_avid(url)
        video_id = _build_video_id(bvid, avid)

        vdir = Path(video_dir)
        vdir.mkdir(parents=True, exist_ok=True)
        meta = {"video_id": video_id, "url": url, "title": url, "bvid": bvid, "avid": avid}
        save_meta_json(vdir, meta)

        return StageResult(
            success=True,
            artifacts={"meta_json": str(vdir / "meta.json"), "video_dir": video_dir},
            metadata={"video_id": video_id, "title": url, "video_dir": video_dir},
        )

    async def download(
        self,
        video_dir: str,
        quality: str = "1080p",
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        from app.processor.downloader import download_video
        return await download_video(video_dir, quality, progress_cb, self.data_dir)

    async def extract_audio(
        self,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        from app.processor.audio import extract_audio
        return await extract_audio(video_dir, progress_cb)
