"""Transcriber configuration and model management API."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter(prefix="/transcribers", tags=["transcribers"])

AVAILABLE_TYPES = [
    {"value": "fast-whisper", "label": "fast-whisper"},
    {"value": "mlx-whisper", "label": "mlx-whisper"},
    {"value": "groq", "label": "Groq"},
]
WHISPER_MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]

_CONFIG_FILE = Path(settings.data_dir) / "transcriber_config.json"

def _load_config():
    default = {
        "transcriber_type": "fast-whisper",
        "whisper_model_size": settings.whisper_model_size or "small",
    }
    if _CONFIG_FILE.exists():
        try:
            loaded = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            default.update(loaded)
        except Exception:
            pass
    return default

_runtime_config = _load_config()

def _save_config():
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(_runtime_config, ensure_ascii=False), encoding="utf-8")


@router.get("/config")
def get_transcriber_config():
    return {
        "transcriber_type": _runtime_config["transcriber_type"],
        "whisper_model_size": _runtime_config["whisper_model_size"],
        "available_types": AVAILABLE_TYPES,
        "whisper_model_sizes": WHISPER_MODEL_SIZES,
        "whisper_builtin_models": {s: s for s in WHISPER_MODEL_SIZES},
        "whisper_custom_models": {},
        "mlx_whisper_available": False,
    }


class TranscriberConfigUpdate(BaseModel):
    transcriber_type: str | None = None
    whisper_model_size: str | None = None


@router.put("/config")
def update_transcriber_config(body: TranscriberConfigUpdate):
    updated = []
    if body.transcriber_type:
        _runtime_config["transcriber_type"] = body.transcriber_type
        updated.append("transcriber_type")
    if body.whisper_model_size:
        _runtime_config["whisper_model_size"] = body.whisper_model_size
        updated.append("whisper_model_size")
    if updated:
        _save_config()
    return {"updated_fields": updated}


@router.get("/models/status")
def get_models_status():
    return {
        "whisper": [
            {"model_size": s, "downloaded": s == _runtime_config["whisper_model_size"],
             "downloading": False}
            for s in WHISPER_MODEL_SIZES
        ],
        "mlx_whisper": [],
        "mlx_available": False,
    }


class DownloadModelPayload(BaseModel):
    model_size: str
    transcriber_type: str = "fast-whisper"


@router.post("/models/download")
def download_model(body: DownloadModelPayload):
    """Stub: model download not implemented. Returns success for development."""
    return {"status": "started", "message": f"Mock: would download {body.model_size}"}


WHISPER_MODELS_FILE = os.path.join(settings.data_dir, "whisper_models.json")


@router.get("/whisper-models")
def list_whisper_models():
    custom = {}
    if os.path.isfile(WHISPER_MODELS_FILE):
        import json
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
    custom = {}
    if os.path.isfile(WHISPER_MODELS_FILE):
        import json
        try:
            with open(WHISPER_MODELS_FILE, encoding="utf-8") as f:
                custom = json.load(f)
        except Exception:
            pass
    custom[body.name] = body.target
    os.makedirs(os.path.dirname(WHISPER_MODELS_FILE) or ".", exist_ok=True)
    import json
    with open(WHISPER_MODELS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}


@router.delete("/whisper-models/{name:path}")
def delete_whisper_model(name: str):
    if os.path.isfile(WHISPER_MODELS_FILE):
        import json
        with open(WHISPER_MODELS_FILE, encoding="utf-8") as f:
            custom = json.load(f)
        custom.pop(name, None)
        with open(WHISPER_MODELS_FILE, "w", encoding="utf-8") as f:
            json.dump(custom, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}
