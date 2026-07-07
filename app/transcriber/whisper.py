"""
Faster-Whisper 本地转写实现。

使用 CTranslate2 加速的 Whisper 模型进行语音转写。
"""
from __future__ import annotations

import json
import os
import warnings
from collections.abc import Callable
from pathlib import Path

from app.schemas.stage import StageResult

warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API.*",
    category=UserWarning,
)


class FasterWhisperTranscriber:
    """本地 Faster-Whisper 转写器。

    支持模型大小: tiny / base / small / medium / large-v3
    支持设备: cpu / cuda / auto（auto 默认走 CPU，避免 Windows 缺 CUDA 运行库时崩溃）
    """

    def __init__(
        self,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "auto",
    ):
        """初始化转写器。

        Args:
            model_size: 模型大小
            device: 计算设备（auto 会选择 CPU，显式 cuda 才使用 GPU）
            compute_type: 计算精度（auto / float16 / int8_float16 / int8）。
                          auto 时根据设备自动选择：CUDA→float16，CPU→int8
        """
        valid_sizes = {"tiny", "base", "small", "medium", "large-v3", "turbo"}
        if model_size not in valid_sizes:
            raise ValueError(
                f"无效的模型大小: {model_size}，可选: {', '.join(sorted(valid_sizes))}"
            )
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _resolve_compute_type(self, device: str, compute_type: str) -> str:
        """根据设备自动选择合适的计算精度。"""
        if compute_type != "auto":
            return compute_type
        # auto 模式走 CPU，避免检测到 CUDA 但缺少 cuDNN/cuBLAS 时导致进程崩溃。
        if device == "auto":
            return "int8"
        if device == "cuda":
            return "float16"
        # cpu → int8（float16 在 CPU 上不支持）
        return "int8"

    def _ensure_model(self):
        """延迟加载模型（首次使用时加载）。"""
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper 未安装。请运行: pip install faster-whisper"
            )

        # auto 走 CPU；只有用户显式配置 cuda 时才尝试 GPU。
        devices_to_try = [self.device] if self.device != "auto" else ["cpu"]
        last_error = None

        for dev in devices_to_try:
            try:
                dev_ct = self._resolve_compute_type(dev, self.compute_type)
                self._model = WhisperModel(
                    self.model_size,
                    device=dev,
                    compute_type=dev_ct,
                )
                return
            except (RuntimeError, ValueError) as e:
                last_error = str(e)
                if "cublas" in last_error.lower() or "cuda" in last_error.lower() or "float16" in last_error.lower():
                    continue  # 降级尝试下一个 device
                raise  # 其他错误直接抛出

        raise RuntimeError(f"无法加载 Whisper 模型: {last_error}")

    async def transcribe(
        self,
        audio_path: str,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """转写音频文件为带时间戳的文本。

        Args:
            audio_path: 音频文件路径
            video_dir: 视频产物目录（输出 transcription.json / .srt）
            progress_cb: 可选进度回调

        Returns:
            StageResult:
                - .artifacts["transcript_json"] = 转写 JSON 路径
                - .artifacts["transcript_srt"] = SRT 字幕路径
                - .metadata 含 full_text, language, segments 数量
        """
        if not os.path.isfile(audio_path):
            return StageResult(
                success=False,
                error=f"音频文件不存在: {audio_path}",
            )

        try:
            self._ensure_model()
        except RuntimeError as e:
            return StageResult(success=False, error=str(e))

        import asyncio

        loop = asyncio.get_running_loop()

        def _sync_transcribe():
            segments_raw, info = self._model.transcribe(
                audio_path,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                ),
            )

            segments = []
            full_text_parts = []
            total_duration = info.duration  # 音频总时长（秒）

            for i, seg in enumerate(segments_raw):
                segments.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                    "confidence": round(seg.avg_logprob, 4) if seg.avg_logprob else None,
                })
                full_text_parts.append(seg.text.strip())

                if progress_cb and total_duration > 0:
                    pct = (seg.end / total_duration) * 100.0
                    progress_cb(min(pct, 99.0))

            if progress_cb:
                progress_cb(100.0)

            return segments, " ".join(full_text_parts), info.language

        try:
            segments, full_text, language = await loop.run_in_executor(
                None, _sync_transcribe
            )
        except Exception as exc:
            return StageResult(success=False, error=f"语音转写失败: {exc}")

        if not segments:
            return StageResult(
                success=False,
                error="转写结果为空，请检查音频文件是否包含有效语音",
            )

        # 保存 JSON 格式
        video_dir_path = Path(video_dir)
        video_dir_path.mkdir(parents=True, exist_ok=True)

        transcript_json = {
            "language": language,
            "duration_seconds": sum(s["end"] - s["start"] for s in segments),
            "segments": segments,
            "full_text": full_text,
        }
        json_path = video_dir_path / "transcription.json"
        json_path.write_text(
            json.dumps(transcript_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 保存 SRT 格式
        srt_path = video_dir_path / "transcription.srt"
        srt_path.write_text(_to_srt(segments), encoding="utf-8")

        return StageResult(
            success=True,
            artifacts={
                "transcript_json": str(json_path),
                "transcript_srt": str(srt_path),
            },
            metadata={
                "full_text": full_text,
                "language": language,
                "segment_count": len(segments),
                "duration_seconds": sum(s["end"] - s["start"] for s in segments),
                "model_size": self.model_size,
            },
        )


def _to_srt(segments: list[dict]) -> str:
    """将转写片段列表转为 SRT 字幕格式。"""

    def _fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time(seg['start'])} --> {_fmt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")

    return "\n".join(lines)
