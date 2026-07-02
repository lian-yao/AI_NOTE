"""
必剪 API 转写实现（备选方案）。

当本地 Whisper 不可用或连续失败时，切换到必剪在线 API 进行转写。
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path

from app.schemas.stage import StageResult
from app.core.config import settings


class BjianTranscriber:
    """必剪在线 API 转写器。

    需要必剪开放平台的 App ID 和 Access Token。
    配置方式：config.yaml 中的 transcriber.bjian 段，或环境变量 BJIAN_APP_ID / BJIAN_ACCESS_TOKEN。
    """

    # 必剪 API 基础 URL（以官方文档为准）
    API_BASE = "https://api.bcut.com"

    def __init__(
        self,
        app_id: str = "",
        access_token: str = "",
    ):
        """
        Args:
            app_id: 必剪 App ID
            access_token: 必剪 Access Token
        """
        self.app_id = app_id or os.getenv("BJIAN_APP_ID", "")
        self.access_token = access_token or os.getenv("BJIAN_ACCESS_TOKEN", "")
        # 优先从 Settings 读取（支持 VN_ 前缀的 .env）
        if not self.app_id:
            self.app_id = settings.bjian_app_id
        if not self.access_token:
            self.access_token = settings.bjian_access_token

    @property
    def _is_configured(self) -> bool:
        """是否已配置 API 凭证。"""
        return bool(self.app_id and self.access_token)

    async def transcribe(
        self,
        audio_path: str,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """使用必剪 API 转写音频。

        Args:
            audio_path: 音频文件路径
            video_dir: 视频产物目录
            progress_cb: 可选进度回调

        Returns:
            StageResult
        """
        if not self._is_configured:
            return StageResult(
                success=False,
                error="必剪 API 未配置：缺少 BJIAN_APP_ID 或 BJIAN_ACCESS_TOKEN",
            )

        if not os.path.isfile(audio_path):
            return StageResult(
                success=False,
                error=f"音频文件不存在: {audio_path}",
            )

        try:
            import httpx
        except ImportError:
            return StageResult(
                success=False,
                error="httpx 未安装。请运行: pip install httpx",
            )

        if progress_cb:
            progress_cb(10.0)

        try:
            # 1. 上传音频获取任务 ID
            task_id = await self._upload_audio(audio_path)

            if progress_cb:
                progress_cb(30.0)

            # 2. 轮询转写结果
            result = await self._poll_result(task_id, progress_cb)

            if progress_cb:
                progress_cb(90.0)

            # 3. 解析并保存结果
            segments = self._parse_result(result)
            full_text = " ".join(s["text"] for s in segments)

            video_dir_path = Path(video_dir)
            video_dir_path.mkdir(parents=True, exist_ok=True)

            transcript_json = {
                "language": result.get("language", "zh"),
                "duration_seconds": sum(s["end"] - s["start"] for s in segments),
                "segments": segments,
                "full_text": full_text,
            }
            json_path = video_dir_path / "transcription.json"
            json_path.write_text(
                json.dumps(transcript_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if progress_cb:
                progress_cb(100.0)

            return StageResult(
                success=True,
                artifacts={
                    "transcript_json": str(json_path),
                },
                metadata={
                    "full_text": full_text,
                    "language": result.get("language", "zh"),
                    "segment_count": len(segments),
                    "transcriber_type": "bjian",
                },
            )

        except httpx.HTTPStatusError as exc:
            return StageResult(
                success=False,
                error=f"必剪 API 请求失败 (HTTP {exc.response.status_code}): {exc}",
            )
        except Exception as exc:
            return StageResult(
                success=False,
                error=f"必剪转写失败: {exc}",
            )

    async def _upload_audio(self, audio_path: str) -> str:
        """上传音频文件，返回任务 ID。"""
        import httpx

        # 注：以下为必剪 API 的预期调用方式（以官方文档为准）
        # 实际接口地址和参数需要根据必剪开放平台文档调整
        async with httpx.AsyncClient(timeout=60) as client:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"{self.API_BASE}/v1/transcribe/upload",
                    headers=headers,
                    files={"file": f},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("task_id", "")

    async def _poll_result(
        self,
        task_id: str,
        progress_cb: Callable[[float], None] | None = None,
        max_wait_seconds: int = 600,
    ) -> dict:
        """轮询转写任务结果。"""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {self.access_token}"}

            for _ in range(max_wait_seconds // 5):
                await asyncio.sleep(5)

                response = await client.get(
                    f"{self.API_BASE}/v1/transcribe/result/{task_id}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                status = data.get("status", "")
                if status == "completed":
                    return data
                if status == "failed":
                    raise RuntimeError(f"必剪转写任务失败: {data.get('error', '未知错误')}")

                # 更新进度
                if progress_cb:
                    task_progress = float(data.get("progress", 30))
                    progress_cb(30.0 + task_progress * 0.6)  # 30%-90%

            raise TimeoutError(f"必剪转写超时（{max_wait_seconds} 秒）")

    def _parse_result(self, result: dict) -> list[dict]:
        """解析必剪 API 返回的转写结果为标准 segments 格式。

        注：需根据必剪 API 实际响应格式调整字段映射。
        """
        # 预期响应中有 utterances 或 segments 列表
        raw_segments = (
            result.get("utterances")
            or result.get("segments")
            or result.get("result", [])
        )

        segments = []
        for item in raw_segments:
            segments.append({
                "start": round(float(item.get("start_time", item.get("start", 0))), 2),
                "end": round(float(item.get("end_time", item.get("end", 0))), 2),
                "text": str(item.get("text", item.get("sentence", ""))).strip(),
                "confidence": item.get("confidence", None),
            })

        return segments
