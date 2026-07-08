"""
自动切换转写器：本地优先，API 兜底。

按流水线文档 5.2 节降级方案：
- 本地 Whisper 连续失败 2 次 → 切换到必剪 API
- 始终优先使用本地转写
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.schemas.stage import StageResult
from app.transcriber.whisper import FasterWhisperTranscriber
from app.transcriber.bjian import BjianTranscriber


def _configured_model_size() -> str:
    configured = "tiny"
    config_file = Path(settings.data_dir) / "transcriber_config.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            configured = str(data.get("whisper_model_size") or configured)
        except Exception:
            pass
    return configured if configured in {"tiny", "base", "small", "medium", "large-v3", "turbo"} else "tiny"


class AutoTranscriber:
    """自动切换转写器。

    策略：
    1. 优先使用本地 Faster-Whisper（速度快、免费）
    2. 本地失败时自动降级到必剪 API
    3. 记录失败次数，用于上层决策
    """

    def __init__(
        self,
        local: FasterWhisperTranscriber | None = None,
        api: BjianTranscriber | None = None,
        local_max_failures: int = 2,
    ):
        """
        Args:
            local: 本地转写器实例
            api: 必剪 API 转写器实例
            local_max_failures: 本地连续失败多少次后切换
        """
        self.local = local or FasterWhisperTranscriber(
            model_size=_configured_model_size(),
            device=settings.whisper_device or "cpu",
        )
        self.api = api or BjianTranscriber()
        self.local_max_failures = local_max_failures
        self._local_failures = 0

    async def transcribe(
        self,
        audio_path: str,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """自动选择并执行转写。

        Args:
            audio_path: 音频文件路径
            video_dir: 视频产物目录
            progress_cb: 可选进度回调

        Returns:
            StageResult
        """
        # 1. 尝试本地转写
        if self._local_failures < self.local_max_failures:
            result = await self.local.transcribe(audio_path, video_dir, progress_cb)
            if result.success:
                self._local_failures = 0  # 成功后重置
                return result

            self._local_failures += 1
            # 如果还没超过阈值，直接返回错误（让上层重试）
            if self._local_failures < self.local_max_failures:
                return result

        # 2. 降级到必剪 API
        result = await self.api.transcribe(audio_path, video_dir, progress_cb)
        if result.success:
            # API 成功后重置本地失败计数（下次优先本地）
            self._local_failures = 0

        return result

    def switch_local(self, model_size: str):
        """热切换本地 Whisper 模型大小。

        重置失败计数并通知底层转写器切换模型，
        下次 transcribe 时自动加载新模型。

        Args:
            model_size: 新的模型大小 (tiny/base/small/medium/large-v3/turbo)
        """
        self._local_failures = 0
        if self.local:
            self.local.reload(model_size)

    def reset(self):
        """重置失败计数（例如用户手动切换了转写方式后调用）。"""
        self._local_failures = 0
