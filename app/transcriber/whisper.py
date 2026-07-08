"""
Faster-Whisper 本地转写实现。

使用 CTranslate2 加速的 Whisper 模型进行语音转写。
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from collections.abc import Callable
from pathlib import Path

from app.schemas.stage import StageResult

warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API.*",
    category=UserWarning,
)


def _setup_cuda_dlls() -> bool:
    """确保 cuBLAS DLL 可被 ctranslate2 加载。

    自动发现 nvidia-cublas-cu12 或 nvidia-cublas-cu11 pip 包的 bin 目录，
    将必要的 DLL 复制到 ctranslate2 包目录下（同级加载策略）。
    返回 True 表示 CUDA DLL 已就绪。
    """
    if sys.platform != "win32":
        return True

    # 支持 CUDA 12.x 和 CUDA 11.x 两套 DLL
    _DLL_VERSIONS = (
        ("cublas64_12.dll", "cublasLt64_12.dll"),   # CUDA 12.x
        ("cublas64_11.dll", "cublasLt64_11.dll"),   # CUDA 11.x
    )

    try:
        import ctranslate2 as _ct2
        _ct2_dir = Path(_ct2.__file__).parent
    except Exception:
        return False

    # 检查是否已有任一版本的 DLL 可用
    for _dll_set in _DLL_VERSIONS:
        if all((_ct2_dir / d).exists() for d in _dll_set):
            return True

    # 尝试发现 nvidia-cublas-cuXX 的 bin 目录
    _cublas_bin = None
    _found_version = None

    # 先尝试 nvidia.cublas 包 (cu12)
    for _pkg_name in ("nvidia.cublas",):
        try:
            _mod = __import__(_pkg_name, fromlist=["__path__"])
            _bin = Path(_mod.__path__[0]) / "bin"
            for _dll_set in _DLL_VERSIONS:
                if (_bin / _dll_set[0]).exists():
                    _cublas_bin = _bin
                    _found_version = _dll_set
                    break
            if _cublas_bin:
                break
        except ImportError:
            pass

    # 回退：扫描 sys.path 中可能的 site-packages 目录
    if _cublas_bin is None:
        for _site in sys.path:
            _site_path = Path(_site)
            for _nvidia_pkg in ("nvidia",):
                _pkg_dir = _site_path / _nvidia_pkg / "cublas" / "bin"
                if _pkg_dir.exists():
                    for _dll_set in _DLL_VERSIONS:
                        if (_pkg_dir / _dll_set[0]).exists():
                            _cublas_bin = _pkg_dir
                            _found_version = _dll_set
                            break
                    if _cublas_bin:
                        break
            if _cublas_bin:
                break

    if _cublas_bin is None:
        return False

    # 复制 DLL 到 ctranslate2 目录
    import shutil
    for _dll in _found_version:
        _src = _cublas_bin / _dll
        if _src.exists() and not (_ct2_dir / _dll).exists():
            try:
                shutil.copy2(str(_src), str(_ct2_dir / _dll))
            except Exception:
                return False

    return all((_ct2_dir / d).exists() for d in _found_version)


_HAS_CUDA_DLLS = _setup_cuda_dlls()


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

    def reload(self, model_size: str):
        """热切换模型（不重启进程）。

        更新模型大小并重置已加载的模型实例，
        下次 transcribe 时自动下载/加载新模型。

        Args:
            model_size: 新的模型大小 (tiny/base/small/medium/large-v3/turbo)

        Raises:
            ValueError: 无效的模型大小
        """
        valid_sizes = {"tiny", "base", "small", "medium", "large-v3", "turbo"}
        if model_size not in valid_sizes:
            raise ValueError(
                f"无效的模型大小: {model_size}，可选: {', '.join(sorted(valid_sizes))}"
            )
        logger = __import__("loguru").logger
        logger.info(f"转写器模型热切换: {self.model_size} → {model_size}")
        self.model_size = model_size
        self._model = None  # 下次 _ensure_model() 重新加载

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

        logger = __import__("loguru").logger

        # 确定尝试的设备列表，CUDA 不可用时自动降级 CPU
        if self.device == "auto":
            # auto: 检测 CUDA，有则用 GPU，无则用 CPU
            _try_cuda = _HAS_CUDA_DLLS
            try:
                import torch
                _try_cuda = _try_cuda and torch.cuda.is_available()
            except ImportError:
                pass
            devices_to_try = ["cuda", "cpu"] if _try_cuda else ["cpu"]
        elif self.device == "cuda":
            if not _HAS_CUDA_DLLS:
                logger.warning(
                    "CUDA 设备已配置但未找到 cuBLAS 库。"
                    "请在设置页 → 本地转写 → GPU 加速中点击安装 GPU 驱动。"
                    "当前将尝试 CUDA，如失败则降级到 CPU。"
                )
                devices_to_try = ["cuda", "cpu"]
            else:
                devices_to_try = ["cuda"]
        else:
            devices_to_try = [self.device]

        last_error = None
        for dev in devices_to_try:
            try:
                dev_ct = self._resolve_compute_type(dev, self.compute_type)
                self._model = WhisperModel(
                    self.model_size,
                    device=dev,
                    compute_type=dev_ct,
                )
                if dev != self.device:
                    # auto → cuda 是自动选择最优设备，不是降级
                    if self.device == "auto":
                        logger.info(f"Whisper 自动选择设备: {dev}")
                    else:
                        logger.warning(
                            f"Whisper 已从 {self.device} 降级到 {dev}"
                            + (f"（原因: {last_error}）" if last_error else "")
                        )
                return
            except (RuntimeError, ValueError) as e:
                last_error = str(e)
                if "cublas" in last_error.lower() or "cuda" in last_error.lower() or "float16" in last_error.lower():
                    continue  # 降级尝试下一个 device
                raise  # 其他错误直接抛出

        _hint = ""
        if not _HAS_CUDA_DLLS and self.device in ("cuda", "auto"):
            _hint = "。提示: pip install nvidia-cublas-cu12 可安装缺失的 CUDA 库"
        raise RuntimeError(f"无法加载 Whisper 模型: {last_error}{_hint}")

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

        _last_pct = [0]  # 用列表避免 nonlocal 声明

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
                    # 每 5% 才回调一次，减少 I/O 开销
                    if int(pct) - _last_pct[0] >= 5 or pct >= 99.0:
                        _last_pct[0] = int(pct)
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
