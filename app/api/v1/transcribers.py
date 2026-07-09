"""Transcriber configuration and model management API."""
from __future__ import annotations
import json
import os
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.core.config import settings
from app.transcriber.model_manager import (
    get_models_status,
    start_download,
    get_download_progress,
    delete_model_cache,
    reset_download,
    _ALL_MODEL_SIZES,
)

router = APIRouter(prefix="/transcribers", tags=["transcribers"])

AVAILABLE_TYPES = [
    {"value": "fast-whisper", "label": "fast-whisper"},
]
_AVAILABLE_TYPE_VALUES = {item["value"] for item in AVAILABLE_TYPES}
WHISPER_MODEL_SIZES = _ALL_MODEL_SIZES

_CONFIG_FILE = Path(settings.data_dir) / "transcriber_config.json"


def _load_config() -> dict:
    """加载转写器配置（文件 + settings 默认值）。"""
    default = {
        "transcriber_type": "fast-whisper",
        "whisper_model_size": settings.whisper_model_size or "small",
        "whisper_device": settings.whisper_device or "auto",
    }
    if _CONFIG_FILE.exists():
        try:
            loaded = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            default.update(loaded)
        except Exception:
            pass
    if default.get("transcriber_type") not in _AVAILABLE_TYPE_VALUES:
        default["transcriber_type"] = "fast-whisper"
    return default


_runtime_config = _load_config()


def _save_config():
    """持久化转写器运行时配置到 JSON 文件。"""
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps(_runtime_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 配置接口 ──


@router.get("/config")
def get_transcriber_config():
    """获取转写器配置（类型、模型大小、可用选项）。"""
    return {
        "transcriber_type": _runtime_config["transcriber_type"],
        "whisper_model_size": _runtime_config["whisper_model_size"],
        "whisper_device": _runtime_config.get("whisper_device", "auto"),
        "available_types": AVAILABLE_TYPES,
        "whisper_model_sizes": WHISPER_MODEL_SIZES,
        "whisper_builtin_models": {s: s for s in WHISPER_MODEL_SIZES},
        "whisper_custom_models": {},
        "mlx_whisper_available": False,
    }


class TranscriberConfigUpdate(BaseModel):
    transcriber_type: str | None = None
    whisper_model_size: str | None = None
    whisper_device: str | None = None


@router.put("/config")
def update_transcriber_config(body: TranscriberConfigUpdate, request: Request):
    """更新转写器运行时配置（自动持久化 + 热更新运行中的编排器）。"""
    updated = []
    old_size = _runtime_config.get("whisper_model_size")
    old_device = _runtime_config.get("whisper_device")
    if body.transcriber_type and body.transcriber_type in _AVAILABLE_TYPE_VALUES:
        _runtime_config["transcriber_type"] = body.transcriber_type
        updated.append("transcriber_type")
    if body.whisper_model_size:
        _runtime_config["whisper_model_size"] = body.whisper_model_size
        updated.append("whisper_model_size")
    if body.whisper_device is not None:
        if body.whisper_device in ("cpu", "cuda", "auto"):
            _runtime_config["whisper_device"] = body.whisper_device
            updated.append("whisper_device")
        else:
            from loguru import logger
            logger.warning(f"无效的 whisper_device 值: {body.whisper_device}，已忽略")
    if updated:
        _save_config()

    # ── 热更新运行中的编排器转写器 ──
    device_changed = body.whisper_device is not None and body.whisper_device != old_device
    if body.whisper_model_size and body.whisper_model_size != old_size:
        try:
            orchestrator = request.app.state.orchestrator
            if hasattr(orchestrator, "transcriber") and hasattr(
                orchestrator.transcriber, "switch_local"
            ):
                # 清除旧模型的下载失败状态
                if old_size:
                    reset_download(old_size)
                # 通知编排器切换模型
                orchestrator.transcriber.switch_local(body.whisper_model_size)
            # ── 热更新 device ──
            if device_changed and hasattr(
                orchestrator.transcriber, "switch_device"
            ):
                orchestrator.transcriber.switch_device(body.whisper_device)
        except Exception:
            import traceback
            from loguru import logger

            logger.warning(
                f"热更新转写器失败（不影响配置保存）:\n{traceback.format_exc()}"
            )

    return {"updated_fields": updated}


# ── 模型状态接口 ──


@router.get("/models/status")
def get_models_status_api():
    """获取所有 Whisper 模型的下载状态（真实扫描 HF 缓存）。"""
    statuses = get_models_status()
    return {
        "whisper": statuses,
        "mlx_whisper": [],
        "mlx_available": False,
    }


# ── 模型下载接口 ──


class DownloadModelPayload(BaseModel):
    model_size: str
    transcriber_type: str = "fast-whisper"


@router.post("/models/download")
def download_model(body: DownloadModelPayload):
    """启动模型下载（后台线程，进度通过 /models/download/{model_size}/progress 查询）。"""
    result = start_download(body.model_size)
    return result


@router.get("/models/download/{model_size}/progress")
def get_model_download_progress(model_size: str):
    """查询单个模型的下载进度（供前端轮询）。"""
    progress = get_download_progress(model_size)
    if progress is None:
        return {"model_size": model_size, "downloading": False,
                "message": "无下载记录", "progress": 0}
    return progress


@router.post("/models/download/{model_size}/reset")
def reset_model_download(model_size: str):
    """重置下载状态（用于重试失败的下载）。"""
    ok = reset_download(model_size)
    return {"model_size": model_size, "reset": ok}


@router.delete("/models/{model_size}/cache")
def delete_model_cache_api(model_size: str):
    """删除指定 Whisper 模型的 HuggingFace 本地缓存。"""
    return delete_model_cache(model_size)


# ── Whisper 自定义模型管理 ──

WHISPER_MODELS_FILE = os.path.join(settings.data_dir, "whisper_models.json")


@router.get("/whisper-models")
def list_whisper_models():
    """列出内建 + 自定义 Whisper 模型。"""
    custom = {}
    if os.path.isfile(WHISPER_MODELS_FILE):
        try:
            with open(WHISPER_MODELS_FILE, encoding="utf-8") as f:
                custom = json.load(f)
        except Exception:
            pass
    return {
        "builtin": {s: s for s in WHISPER_MODEL_SIZES},
        "custom": custom,
    }


class AddWhisperModelPayload(BaseModel):
    name: str
    target: str


@router.post("/whisper-models")
def add_whisper_model(body: AddWhisperModelPayload):
    """添加自定义 Whisper 模型。"""
    custom = {}
    if os.path.isfile(WHISPER_MODELS_FILE):
        try:
            with open(WHISPER_MODELS_FILE, encoding="utf-8") as f:
                custom = json.load(f)
        except Exception:
            pass
    custom[body.name] = body.target
    os.makedirs(os.path.dirname(WHISPER_MODELS_FILE) or ".", exist_ok=True)
    with open(WHISPER_MODELS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}


@router.delete("/whisper-models/{name:path}")
def delete_whisper_model(name: str):
    """删除自定义 Whisper 模型。"""
    if os.path.isfile(WHISPER_MODELS_FILE):
        with open(WHISPER_MODELS_FILE, encoding="utf-8") as f:
            custom = json.load(f)
        custom.pop(name, None)
        with open(WHISPER_MODELS_FILE, "w", encoding="utf-8") as f:
            json.dump(custom, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}
