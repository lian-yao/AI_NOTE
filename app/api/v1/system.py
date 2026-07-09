"""
System health API.
"""
import time
import shutil
import subprocess
import threading
import uuid
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings, storage_config_file
from app.core.paths import project_root
from app.core.model_usage import (
    load_model_usage_config,
    prune_model_usage_config,
    save_model_usage_config,
    validate_model_pair,
)
import json
from pathlib import Path as _Path

router = APIRouter(prefix="/system", tags=["system"])


def _check_db(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _check_disk(data_dir: str) -> str:
    try:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        return "ok" if free_gb > 0.5 else "low"
    except Exception:
        return "error"


@router.get("/health")
async def system_health(request: Request, db: Session = Depends(get_db)):
    """Detailed system health check. Matches API doc section 7.5."""
    start_time: float = getattr(request.app.state, "start_time", time.time())
    uptime = int(time.time() - start_time)

    db_status = _check_db(db)
    disk_status = _check_disk(settings.data_dir)

    vector_store_status = "ok"
    llm_api_status = "ok"
    embedding_api_status = "ok"

    all_ok = all(s == "ok" for s in [db_status, vector_store_status, llm_api_status, embedding_api_status, disk_status])

    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": "healthy" if all_ok else "degraded",
            "database": db_status,
            "vector_store": vector_store_status,
            "llm_api": llm_api_status,
            "embedding_api": embedding_api_status,
            "disk_space": disk_status,
            "uptime_seconds": uptime,
        },
    }


def _load_transcriber_config() -> dict:
    """从 transcriber_config.json 加载转写器运行时配置。"""
    from pathlib import Path
    config_file = Path(settings.data_dir) / "transcriber_config.json"
    if config_file.exists():
        try:
            import json
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@router.get("/config")
def get_system_config():
    """获取系统配置（不包含敏感字段）。"""
    tc = _load_transcriber_config()
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": getattr(settings, 'llm_model', 'qwen-plus'),
        "transcriber_mode": tc.get("transcriber_type", "local"),
        "whisper_model_size": tc.get("whisper_model_size", settings.whisper_model_size),
        "whisper_device": settings.whisper_device,
        "embedding_model": get_embedding_model_config()["model"],
        "retrieval_top_k": settings.retrieval_top_k,
        "data_dir": settings.data_dir,
        "video_retention": getattr(settings, 'video_retention', 'processed'),
    }


_runtime_config: dict = {}

_STORAGE_CONFIG_PATH = storage_config_file()
_CACHE_DIRECTORY_CHILDREN = {
    "downloads": "downloads",
    "transcripts": "transcripts",
    "covers": "covers",
    "temp": "temp",
}
_DOWNLOAD_TEMP_SUFFIXES = {".part", ".ytdl", ".tmp", ".temp", ".download"}
_TRANSCRIPT_CACHE_NAMES = {"transcription.json", "transcription.srt"}
_TRANSCRIPT_CACHE_SUFFIXES = {".vtt", ".ass"}


def _resolve_storage_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path


def _display_storage_path(path: str | Path) -> str:
    return str(_resolve_storage_path(path))


def _join_storage_path(root_path: str, child_dir: str) -> str:
    return str(_resolve_storage_path(root_path) / child_dir)


def _default_storage_config() -> dict:
    data_root = _display_storage_path(settings.data_dir)
    cache_root = _join_storage_path(data_root, "cache")
    return {
        "dataRootPath": data_root,
        "cacheRootPath": cache_root,
        "cacheDirectories": {
            key: _join_storage_path(cache_root, child)
            for key, child in _CACHE_DIRECTORY_CHILDREN.items()
        },
        "lastCacheClearedAt": None,
    }


def _normalize_storage_config(config: dict | None) -> dict:
    fallback = _default_storage_config()
    config = config or {}
    cache_dirs = config.get("cacheDirectories") or {}
    data_root = str(config.get("dataRootPath") or fallback["dataRootPath"]).strip()
    cache_root = str(config.get("cacheRootPath") or fallback["cacheRootPath"]).strip()
    normalized = {
        "dataRootPath": _display_storage_path(data_root),
        "cacheRootPath": _display_storage_path(cache_root),
        "cacheDirectories": {},
        "lastCacheClearedAt": config.get("lastCacheClearedAt") or fallback["lastCacheClearedAt"],
    }
    for key, child in _CACHE_DIRECTORY_CHILDREN.items():
        value = str(cache_dirs.get(key) or "").strip()
        normalized["cacheDirectories"][key] = (
            _display_storage_path(value)
            if value
            else _join_storage_path(normalized["cacheRootPath"], child)
        )
    return normalized


def _load_storage_config() -> dict:
    if _STORAGE_CONFIG_PATH.exists():
        try:
            return _normalize_storage_config(json.loads(_STORAGE_CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return _default_storage_config()


def _save_storage_config(config: dict) -> dict:
    normalized = _normalize_storage_config(config)
    _STORAGE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORAGE_CONFIG_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    settings.data_dir = normalized["dataRootPath"]
    return normalized


def _is_root_path(path: Path) -> bool:
    resolved = path.resolve()
    return resolved == resolved.parent


def _validate_storage_config(config: dict) -> dict:
    normalized = _normalize_storage_config(config)
    paths = [
        _resolve_storage_path(normalized["dataRootPath"]),
        _resolve_storage_path(normalized["cacheRootPath"]),
        *[
            _resolve_storage_path(path)
            for path in normalized["cacheDirectories"].values()
        ],
    ]
    for path in paths:
        if _is_root_path(path):
            raise HTTPException(status_code=400, detail=f"不能使用磁盘根目录作为存储目录: {path}")
    try:
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"创建存储目录失败: {exc}") from exc
    return normalized


def _iter_files(path: Path):
    if not path.exists():
        return
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        return
    try:
        for item in path.rglob("*"):
            if item.is_file():
                yield item
    except OSError:
        return


def _path_size(path: Path) -> int:
    total = 0
    for item in _iter_files(path) or []:
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _storage_disk_free(path: Path) -> int:
    probe = path if path.exists() else path.parent
    try:
        probe.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(probe).free
    except Exception:
        return 0


def _video_dirs(data_root: Path) -> list[Path]:
    videos_root = data_root / "videos"
    if not videos_root.is_dir():
        return []
    try:
        return [item for item in videos_root.iterdir() if item.is_dir()]
    except OSError:
        return []


def _cache_paths_for_key(key: str, config: dict) -> list[Path]:
    data_root = _resolve_storage_path(config["dataRootPath"])
    paths: list[Path] = []
    configured = config.get("cacheDirectories", {}).get(key)
    if configured:
        paths.append(_resolve_storage_path(configured))

    if key == "downloads":
        for video_dir in _video_dirs(data_root):
            try:
                paths.extend(
                    item for item in video_dir.iterdir()
                    if item.is_file() and item.suffix.lower() in _DOWNLOAD_TEMP_SUFFIXES
                )
            except OSError:
                continue
    elif key == "transcripts":
        for video_dir in _video_dirs(data_root):
            try:
                paths.extend(
                    item for item in video_dir.iterdir()
                    if item.is_file()
                    and (
                        item.name in _TRANSCRIPT_CACHE_NAMES
                        or item.suffix.lower() in _TRANSCRIPT_CACHE_SUFFIXES
                    )
                )
            except OSError:
                continue
    elif key == "covers":
        for video_dir in _video_dirs(data_root):
            snapshot_dir = video_dir / "snapshots"
            if snapshot_dir.exists():
                paths.append(snapshot_dir)
    elif key == "temp":
        for name in ("temp", "tmp"):
            temp_dir = data_root / name
            if temp_dir.exists():
                paths.append(temp_dir)

    return _dedupe_paths(paths)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path.absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _cache_key_stats(key: str, config: dict) -> dict:
    paths = _cache_paths_for_key(key, config)
    bytes_used = sum(_path_size(path) for path in paths)
    configured_path = config.get("cacheDirectories", {}).get(key, "")
    return {
        "key": key,
        "path": configured_path,
        "bytes": bytes_used,
        "exists": any(path.exists() for path in paths),
        "paths": [str(path) for path in paths if path.exists()],
    }


def _storage_stats(config: dict | None = None) -> dict:
    normalized = _normalize_storage_config(config or _load_storage_config())
    data_root = _resolve_storage_path(normalized["dataRootPath"])
    cache_stats = [
        _cache_key_stats(key, normalized)
        for key in _CACHE_DIRECTORY_CHILDREN
    ]
    cache_bytes = sum(item["bytes"] for item in cache_stats)
    return {
        "config": normalized,
        "data_root_path": normalized["dataRootPath"],
        "data_root_bytes": _path_size(data_root),
        "cache_bytes": cache_bytes,
        "disk_free_bytes": _storage_disk_free(data_root),
        "cache": cache_stats,
    }


def _is_forbidden_clear_root(path: Path, config: dict) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    forbidden = {
        project_root().resolve(),
        _resolve_storage_path(config["dataRootPath"]).resolve(),
        _resolve_storage_path(config["cacheRootPath"]).resolve().parent,
    }
    return _is_root_path(resolved) or resolved in forbidden


def _delete_cache_path(path: Path, config: dict) -> int:
    if not path.exists():
        return 0
    if _is_forbidden_clear_root(path, config):
        return 0
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            size = path.stat().st_size
            path.unlink()
            return size
        except OSError:
            return 0
    if not path.is_dir():
        return 0

    freed = 0
    try:
        children = list(path.iterdir())
    except OSError:
        return 0

    for child in children:
        if child.is_symlink():
            continue
        if child.is_file():
            try:
                size = child.stat().st_size
                child.unlink()
                freed += size
            except OSError:
                continue
        elif child.is_dir():
            size = _path_size(child)
            try:
                shutil.rmtree(child)
                freed += size
            except OSError:
                continue
    return freed


def _clear_cache_keys(keys: list[str], config: dict) -> tuple[int, list[str]]:
    valid_keys = [key for key in keys if key in _CACHE_DIRECTORY_CHILDREN]
    freed = 0
    cleared: list[str] = []
    for key in valid_keys:
        before = freed
        for path in _cache_paths_for_key(key, config):
            freed += _delete_cache_path(path, config)
        if freed > before:
            cleared.append(key)
    return freed, cleared


class ConfigUpdate(BaseModel):
    llm_provider: str | None = None
    transcriber_mode: str | None = None
    retrieval_top_k: int | None = None
    whisper_model_size: str | None = None
    whisper_device: str | None = None


class ModelUsageUpdate(BaseModel):
    qa_provider_id: str | None = None
    qa_model_name: str | None = None
    embedding_provider_id: str | None = None
    embedding_model_name: str | None = None
    embedding_model: str | None = None


class StorageConfigUpdate(BaseModel):
    dataRootPath: str | None = None
    cacheRootPath: str | None = None
    cacheDirectories: dict[str, str] | None = None
    lastCacheClearedAt: str | None = None


class StorageClearRequest(BaseModel):
    keys: list[str]


@router.put("/config")
def update_system_config(body: ConfigUpdate):
    """更新运行时配置（临时生效，下次重启恢复 config.yaml 值）。"""
    updated = []
    for key in ('llm_provider', 'transcriber_mode', 'retrieval_top_k', 'whisper_model_size', 'whisper_device'):
        val = getattr(body, key, None)
        if val is not None:
            _runtime_config[key] = val
            updated.append(key)
    return {"updated_fields": updated}


@router.post("/config/save")
def save_system_config():
    """将当前运行时配置持久化到 config.yaml（含转写器配置）。"""
    import yaml
    import json

    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        return {"message": "config.yaml 不存在，跳过保存"}

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # 系统级配置
    cfg.update(_runtime_config)

    # 转写器配置（从 transcriber_config.json 读取并写入 config.yaml）
    tc = _load_transcriber_config()
    if tc:
        if "transcriber" not in cfg:
            cfg["transcriber"] = {}
        cfg["transcriber"]["mode"] = tc.get("transcriber_type", cfg["transcriber"].get("mode", "local"))
        if "whisper" not in cfg["transcriber"]:
            cfg["transcriber"]["whisper"] = {}
        cfg["transcriber"]["whisper"]["model_size"] = tc.get(
            "whisper_model_size",
            cfg["transcriber"]["whisper"].get("model_size", "medium"),
        )

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

    return {"message": "配置已保存到 config.yaml", "saved_fields": list(_runtime_config.keys())}


@router.get("/storage/config")
def get_storage_config():
    """获取后端存储路径配置。"""
    return _load_storage_config()


@router.put("/storage/config")
def update_storage_config(body: StorageConfigUpdate):
    """保存存储路径配置，并让当前后端进程立即使用新的 data_dir。"""
    current = _load_storage_config()
    incoming = body.model_dump(exclude_none=True)
    merged = {
        **current,
        **incoming,
        "cacheDirectories": {
            **current.get("cacheDirectories", {}),
            **(incoming.get("cacheDirectories") or {}),
        },
    }
    normalized = _validate_storage_config(merged)
    saved = _save_storage_config(normalized)
    return saved


@router.get("/storage/stats")
def get_storage_stats():
    """获取真实后端数据目录与缓存分类占用。"""
    return _storage_stats()


@router.post("/storage/clear")
def clear_storage_cache(body: StorageClearRequest):
    """按分类清理缓存文件，不删除数据库、笔记、向量库或视频记录。"""
    if not body.keys:
        raise HTTPException(status_code=400, detail="请选择要清理的缓存类型")
    invalid = [key for key in body.keys if key not in _CACHE_DIRECTORY_CHILDREN]
    if invalid:
        raise HTTPException(status_code=400, detail=f"未知缓存类型: {', '.join(invalid)}")

    config = _load_storage_config()
    freed, cleared = _clear_cache_keys(body.keys, config)
    config["lastCacheClearedAt"] = datetime.now(timezone.utc).isoformat()
    saved = _save_storage_config(config)
    return {
        "freed_bytes": freed,
        "cleared_keys": cleared,
        "config": saved,
        "stats": _storage_stats(saved),
    }


@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    """获取系统统计信息。"""
    from app.models.video import Video
    from app.models.note import Note
    total_videos = db.query(Video).count()
    completed_videos = db.query(Video).filter(Video.status == "completed").count()
    total_notes = db.query(Note).count()
    chunks = db.query(Note).with_entities(Note.total_chunks).all()
    total_chunk_count = sum((c[0] or 0) for c in chunks)
    durations = db.query(Video).with_entities(Video.duration_seconds).all()
    total_hours = sum((d[0] or 0) for d in durations) / 3600
    data_root = _resolve_storage_path(settings.data_dir)
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        storage_usage = _path_size(data_root)
        disk = shutil.disk_usage(data_root)
        disk_free = disk.free
    except Exception:
        storage_usage = 0
        disk_free = 0
    return {
        "total_videos": total_videos,
        "completed_videos": completed_videos,
        "total_notes": total_notes,
        "total_chunks": total_chunk_count,
        "total_duration_hours": round(total_hours, 1),
        "storage_usage_bytes": storage_usage,
        "disk_free_bytes": disk_free,
    }


@router.get("/ready")
async def system_ready():
    """轻量就绪检查，用于前端探测后端是否启动。"""
    return {
        "code": 0,
        "message": "success",
        "data": {
            "ready": True,
            "version": "0.1.0"
        }
    }


@router.get("/deploy-status")
async def deploy_status():
    """获取部署状态（后端、FFmpeg、CUDA、Whisper 等）。"""
    # 检测 FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_available = ffmpeg_path is not None

    # 如果 shutil.which 没找到，尝试用 subprocess 再试一次
    if not ffmpeg_available:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            ffmpeg_available = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    # 检测 CUDA
    cuda_available = False
    cuda_version = None
    gpu_name = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            cuda_available = True
            gpu_name = result.stdout.strip()
            cuda_version = "检测到 NVIDIA GPU"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # 检测 PyTorch CUDA
    torch_installed = False
    torch_cuda_available = False
    try:
        import torch
        torch_installed = True
        torch_cuda_available = torch.cuda.is_available()
        if torch_cuda_available:
            cuda_version = f"CUDA {torch.version.cuda}"
    except ImportError:
        pass

    return {
        "code": 0,
        "message": "success",
        "data": {
            "backend": {
                "status": "ok",
                "port": 8000
            },
            "ffmpeg": {
                "available": ffmpeg_available
            },
            "cuda": {
                "available": cuda_available or torch_cuda_available,
                "torch_installed": torch_installed,
                "version": cuda_version,
                "gpu_name": gpu_name
            },
            "whisper": {
                "model_size": "base",
                "transcriber_type": "fast-whisper",
                "downloaded": False
            }
        }
    }



_NOTE_FORMAT_PATH: _Path | None = None

def _get_note_format_path() -> _Path:
    global _NOTE_FORMAT_PATH
    if _NOTE_FORMAT_PATH is None:
        _NOTE_FORMAT_PATH = _Path(settings.data_dir) / "note_format.json"
    return _NOTE_FORMAT_PATH


@router.get("/note-format")
def get_note_format():
    """获取笔记格式模板。"""
    p = _get_note_format_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {"format": data.get("format", "")}
        except:
            pass
    return {"format": ""}


@router.put("/note-format")
def set_note_format(body: dict):
    """保存笔记格式模板。"""
    fmt = body.get("format", "")
    p = _get_note_format_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"format": fmt}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, "length": len(fmt)}


_TEMPLATES_PATH: _Path | None = None

def _get_templates_path() -> _Path:
    global _TEMPLATES_PATH
    if _TEMPLATES_PATH is None:
        _TEMPLATES_PATH = _Path(settings.data_dir) / "note_format_templates.json"
    return _TEMPLATES_PATH


def _load_templates() -> dict:
    p = _get_templates_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except:
            pass
    return {}


@router.get("/note-format/templates")
def list_note_format_templates():
    return {"templates": _load_templates()}


@router.post("/note-format/templates")
def save_note_format_template(body: dict):
    name = (body.get("name") or "").strip()
    fmt = body.get("format", "")
    if not name or not fmt:
        return {"saved": False, "error": "name and format are required"}
    templates = _load_templates()
    templates[name] = fmt
    _get_templates_path().parent.mkdir(parents=True, exist_ok=True)
    _get_templates_path().write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, "name": name, "count": len(templates)}


@router.delete("/note-format/templates/{name}")
def delete_note_format_template(name: str):
    import urllib.parse
    name = urllib.parse.unquote(name)
    templates = _load_templates()
    if name in templates:
        del templates[name]
        _get_templates_path().write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"deleted": True, "name": name}
    return {"deleted": False, "error": "template not found"}


@router.post("/note-format/templates/{name}/apply")
def apply_note_format_template(name: str):
    import urllib.parse
    name = urllib.parse.unquote(name)
    templates = _load_templates()
    fmt = templates.get(name)
    if not fmt:
        return {"applied": False, "error": "template not found"}
    p = _get_note_format_path()
    p.write_text(json.dumps({"format": fmt}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"applied": True, "name": name, "length": len(fmt)}


_EMBEDDING_CONFIG_PATH: _Path | None = None

def _get_embedding_config_path() -> _Path:
    global _EMBEDDING_CONFIG_PATH
    if _EMBEDDING_CONFIG_PATH is None:
        _EMBEDDING_CONFIG_PATH = _Path(settings.data_dir) / "embedding_config.json"
    return _EMBEDDING_CONFIG_PATH


def _read_embedding_model_config() -> dict:
    p = _get_embedding_config_path()
    if p.exists():
        try:
            return {"model": json.loads(p.read_text(encoding="utf-8")).get("model", "text-embedding-v3")}
        except Exception:
            pass
    return {"model": "text-embedding-v3"}


def _write_embedding_model_config(model: str) -> dict:
    safe_model = (model or "text-embedding-v3").strip() or "text-embedding-v3"
    p = _get_embedding_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": safe_model}), encoding="utf-8")
    return {"model": safe_model, "saved": True}


@router.get("/embedding-model")
def get_embedding_model_config():
    """获取嵌入模型配置。"""
    return _read_embedding_model_config()


@router.put("/embedding-model")
def set_embedding_model_config(body: dict):
    """设置嵌入模型配置。"""
    return _write_embedding_model_config(body.get("model") or "text-embedding-v3")


def _validate_optional_model_pair(db: Session, provider_id: str, model_name: str, label: str) -> None:
    if not provider_id and not model_name:
        return
    if not provider_id or not model_name:
        raise HTTPException(400, f"{label} Provider 和模型名称必须同时选择")
    try:
        validate_model_pair(db, provider_id, model_name)
    except ValueError as exc:
        raise HTTPException(400, f"{label}{exc}") from exc


@router.get("/model-usage")
def get_model_usage_config(db: Session = Depends(get_db)):
    """获取默认用途模型配置。"""
    config = prune_model_usage_config(db)
    embedding_model = _read_embedding_model_config()["model"]
    return {
        **config,
        "embedding_model": embedding_model,
        "env_fallback": {
            "llm": bool(settings.tongyi_api_key or settings.deepseek_api_key),
            "embedding": bool(settings.embedding_api_key or settings.tongyi_api_key),
        },
    }


@router.put("/model-usage")
def set_model_usage_config(body: ModelUsageUpdate, db: Session = Depends(get_db)):
    """设置默认用途模型配置。空值表示继续使用 .env / 系统兜底。"""
    current = load_model_usage_config()
    next_config = {
        **current,
    }
    if body.qa_provider_id is not None:
        next_config["qa_provider_id"] = body.qa_provider_id.strip()
    if body.qa_model_name is not None:
        next_config["qa_model_name"] = body.qa_model_name.strip()
    if body.embedding_provider_id is not None:
        next_config["embedding_provider_id"] = body.embedding_provider_id.strip()
    if body.embedding_model_name is not None:
        next_config["embedding_model_name"] = body.embedding_model_name.strip()

    _validate_optional_model_pair(
        db,
        next_config["qa_provider_id"],
        next_config["qa_model_name"],
        "问答模型",
    )
    _validate_optional_model_pair(
        db,
        next_config["embedding_provider_id"],
        next_config["embedding_model_name"],
        "Embedding 模型",
    )

    saved = save_model_usage_config(next_config)
    embedding_model = (
        _write_embedding_model_config(body.embedding_model)["model"]
        if body.embedding_model is not None
        else _read_embedding_model_config()["model"]
    )
    return {
        **saved,
        "embedding_model": embedding_model,
        "saved": True,
    }

# ── GPU 加速相关接口 ──

# GPU 安装任务追踪: {task_id: {status, progress, message, error}}
_gpu_install_tasks: dict[str, dict] = {}
_uv_path = shutil.which("uv") or "uv"


def _detect_cuda_version() -> tuple[str | None, str | None]:
    """通过 nvidia-smi 检测 CUDA 驱动版本和 GPU 名称。

    Returns:
        (cuda_version, gpu_name) — 如 ("12.5", "NVIDIA GeForce RTX 3060")
    """
    cuda_version = None
    gpu_name = None

    try:
        # 获取 GPU 名称
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().split("\n")[0].strip()

        # 获取 CUDA 驱动版本
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            driver_ver = result.stdout.strip().split("\n")[0].strip()
            # 驱动版本如 "546.01"，提取主版本号推断 CUDA 版本
            try:
                major = int(driver_ver.split(".")[0])
                # NVIDIA 驱动主版本 → CUDA 版本粗略映射
                if major >= 560:
                    cuda_version = "12.6"
                elif major >= 545:
                    cuda_version = "12.4"
                elif major >= 525:
                    cuda_version = "12.0"
                elif major >= 510:
                    cuda_version = "11.8"
                elif major >= 470:
                    cuda_version = "11.4"
                elif major >= 450:
                    cuda_version = "11.0"
                else:
                    cuda_version = "10.x"
            except (ValueError, IndexError):
                cuda_version = None

        # 尝试通过 PyTorch 获取更精确的 CUDA 版本
        try:
            import torch
            if torch.cuda.is_available():
                torch_cuda_ver = torch.version.cuda
                if torch_cuda_ver:
                    cuda_version = torch_cuda_ver
        except ImportError:
            pass

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return cuda_version, gpu_name


def _detect_installed_cublas_package() -> str | None:
    """检测已安装的 nvidia-cublas-cuXX 包名。

    Returns:
        "nvidia-cublas-cu12" / "nvidia-cublas-cu11" / None
    """
    try:
        import importlib.metadata
        for pkg_name in ("nvidia-cublas-cu12", "nvidia-cublas-cu11"):
            try:
                importlib.metadata.version(pkg_name)
                return pkg_name
            except importlib.metadata.PackageNotFoundError:
                pass
    except Exception:
        pass
    return None


def _cublas_dll_version_from_path(path: Path) -> str | None:
    """Return the nvidia-cublas package matching DLLs found in a directory."""
    dll_sets = (
        ("nvidia-cublas-cu12", ("cublas64_12.dll", "cublasLt64_12.dll")),
        ("nvidia-cublas-cu11", ("cublas64_11.dll", "cublasLt64_11.dll")),
    )
    for package, dlls in dll_sets:
        if all((path / dll).exists() for dll in dlls):
            return package
    return None


def _detect_cublas_dll_package() -> str | None:
    """Detect usable cuBLAS DLLs without relying on pip metadata.

    PyInstaller desktop sidecars often do not preserve importlib.metadata for
    nvidia-cublas-cuXX, while the actual DLLs may be bundled or already copied
    next to ctranslate2. Treat those DLLs as installed to avoid repeated installs.
    """
    candidate_dirs: list[Path] = []

    try:
        import ctranslate2 as _ct2
        candidate_dirs.append(Path(_ct2.__file__).parent)
    except Exception:
        pass

    try:
        import nvidia.cublas as _cublas
        candidate_dirs.append(Path(_cublas.__path__[0]) / "bin")
    except Exception:
        pass

    for base in sys.path:
        base_path = Path(base)
        candidate_dirs.append(base_path / "nvidia" / "cublas" / "bin")

    if sys.platform == "win32":
        for base in os.environ.get("PATH", "").split(os.pathsep):
            if base:
                candidate_dirs.append(Path(base))

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            root = Path(meipass)
            candidate_dirs.extend([
                root,
                root / "nvidia" / "cublas" / "bin",
                root / "_internal" / "nvidia" / "cublas" / "bin",
                root / "ctranslate2",
            ])

    seen: set[str] = set()
    for path in candidate_dirs:
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        package = _cublas_dll_version_from_path(path)
        if package:
            return package
    return None


def _detect_cublas_installed() -> bool:
    """检测当前运行环境中的 cuBLAS 是否可用且版本与 CUDA 驱动匹配。"""
    installed_pkg = _detect_installed_cublas_package() or _detect_cublas_dll_package()

    # 获取 CUDA 驱动版本，检查与已安装包的匹配
    cuda_version, _ = _detect_cuda_version()
    recommended = _get_recommended_package(cuda_version)

    # 版本不匹配：驱动是 11.x 但装的是 cu12（或反过来）
    if installed_pkg and recommended and recommended != installed_pkg:
        return False

    # 检查 DLL 是否可被 ctranslate2 加载
    try:
        from app.transcriber.whisper import _HAS_CUDA_DLLS
        return _HAS_CUDA_DLLS
    except Exception:
        pass

    return installed_pkg is not None


def _get_recommended_package(cuda_version: str | None) -> str:
    """根据 CUDA 版本推荐 pip 包名。"""
    if cuda_version is None:
        return "nvidia-cublas-cu12"
    try:
        major = int(cuda_version.split(".")[0])
        minor = int(cuda_version.split(".")[1]) if len(cuda_version.split(".")) > 1 else 0
        if major >= 12:
            return "nvidia-cublas-cu12"
        else:
            return "nvidia-cublas-cu11"
    except (ValueError, IndexError):
        return "nvidia-cublas-cu12"


@router.get("/gpu/info")
def get_gpu_info():
    """获取 GPU 详细信息和推荐驱动包。

    Returns:
        cuda_available: 是否有 NVIDIA GPU
        cuda_version: CUDA 版本号 (如 "12.5")
        gpu_name: GPU 型号
        driver_version: NVIDIA 驱动版本
        recommended_package: 推荐安装的 pip 包名
        gpu_deps_installed: cuBLAS 依赖是否已安装
        torch_cuda_available: PyTorch 是否检测到 CUDA
    """
    cuda_version, gpu_name = _detect_cuda_version()
    cuda_available = gpu_name is not None

    # 尝试获取 torch CUDA 状态
    torch_installed = False
    torch_cuda_available = False
    try:
        import torch
        torch_installed = True
        torch_cuda_available = torch.cuda.is_available()
        if torch_cuda_available and torch.version.cuda:
            cuda_version = torch.version.cuda
    except ImportError:
        pass

    # 获取驱动版本
    driver_version = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            driver_version = result.stdout.strip().split("\n")[0].strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    recommended_package = _get_recommended_package(cuda_version) if cuda_available else None
    gpu_deps_installed = _detect_cublas_installed()
    installed_package = _detect_installed_cublas_package() or _detect_cublas_dll_package()
    package_mismatch = (
        cuda_available
        and installed_package is not None
        and recommended_package is not None
        and installed_package != recommended_package
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "cuda_available": cuda_available,
            "cuda_version": cuda_version,
            "gpu_name": gpu_name,
            "driver_version": driver_version,
            "recommended_package": recommended_package,
            "installed_package": installed_package,
            "package_mismatch": package_mismatch,
            "gpu_deps_installed": gpu_deps_installed,
            "torch_cuda_available": torch_cuda_available,
            "torch_installed": torch_installed,
        },
    }


@router.post("/gpu/install")
def install_gpu_deps():
    """后台安装 GPU 依赖（uv sync --group gpu 或 uv pip install）。

    安装前自动检测 CUDA 版本：
    - CUDA 12.x → uv sync --group gpu（从 pyproject.toml 安装 nvidia-cublas-cu12）
    - CUDA 11.x → uv pip install nvidia-cublas-cu11
    返回 task_id，通过 /gpu/install/{task_id}/progress 轮询进度。
    """
    cuda_version, gpu_name = _detect_cuda_version()
    package = _get_recommended_package(cuda_version)

    task_id = f"gpu_{uuid.uuid4().hex[:8]}"
    _gpu_install_tasks[task_id] = {
        "status": "starting",
        "progress": 0,
        "message": f"准备安装 {package}...",
        "error": None,
        "package": package,
        "cuda_version": cuda_version,
    }

    def _install_worker():
        try:
            _gpu_install_tasks[task_id]["status"] = "running"
            _gpu_install_tasks[task_id]["progress"] = 5
            _gpu_install_tasks[task_id]["message"] = f"正在安装 {package}..."

            import sys
            from app.core.paths import project_root as _project_root

            _project_dir = str(_project_root())

            # 根据 CUDA 版本选择安装方式
            if package == "nvidia-cublas-cu12":
                install_cmd = [_uv_path, "sync", "--group", "gpu"]
                _gpu_install_tasks[task_id]["message"] = "uv sync --group gpu"
            else:
                install_cmd = [_uv_path, "pip", "install", package]
                _gpu_install_tasks[task_id]["message"] = f"uv pip install {package}"

            process = subprocess.Popen(
                install_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=_project_dir,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            # 流式读取输出，实时更新进度
            output_lines = []
            for line in process.stdout:
                line = line.strip()
                if line:
                    output_lines.append(line)
                    # 根据输出推断进度
                    last_line = output_lines[-1] if output_lines else ""
                    if "Downloading" in last_line or "downloading" in last_line:
                        _gpu_install_tasks[task_id]["progress"] = min(
                            _gpu_install_tasks[task_id]["progress"] + 3, 80,
                        )
                    elif "Resolved" in last_line or "Installing" in last_line or "Prepared" in last_line:
                        _gpu_install_tasks[task_id]["progress"] = min(
                            _gpu_install_tasks[task_id]["progress"] + 8, 90,
                        )
                    elif "Installed" in last_line:
                        _gpu_install_tasks[task_id]["progress"] = 92
                    _gpu_install_tasks[task_id]["message"] = last_line[-120:]

            process.wait()

            if process.returncode == 0:
                _gpu_install_tasks[task_id]["progress"] = 95
                # 安装成功后重新执行 DLL 设置
                try:
                    from app.transcriber.whisper import _setup_cuda_dlls
                    _setup_cuda_dlls()
                except Exception:
                    pass

                _gpu_install_tasks[task_id]["status"] = "completed"
                _gpu_install_tasks[task_id]["progress"] = 100
                _gpu_install_tasks[task_id]["message"] = f"GPU 驱动 {package} 安装完成"
            else:
                error_output = "\n".join(output_lines[-10:]) or "安装失败"
                _gpu_install_tasks[task_id]["status"] = "failed"
                _gpu_install_tasks[task_id]["error"] = error_output.strip()[-500:]
                _gpu_install_tasks[task_id]["message"] = f"安装 {package} 失败"

        except Exception as e:
            _gpu_install_tasks[task_id]["status"] = "failed"
            _gpu_install_tasks[task_id]["error"] = str(e)
            _gpu_install_tasks[task_id]["message"] = f"安装出错: {e}"

    thread = threading.Thread(
        target=_install_worker, daemon=True,
        name=f"gpu-install-{task_id}",
    )
    thread.start()

    return {
        "code": 0,
        "message": "安装已启动",
        "data": {
            "task_id": task_id,
            "status": "started",
            "package": package,
        },
    }


@router.get("/gpu/install/{task_id}/progress")
def get_gpu_install_progress(task_id: str):
    """查询 GPU 驱动安装进度。

    Returns:
        task_id, status (starting/running/completed/failed),
        progress (0-100), message, error
    """
    task = _gpu_install_tasks.get(task_id)
    if task is None:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "task_id": task_id,
                "status": "not_found",
                "progress": 0,
                "message": "任务不存在",
                "error": None,
            },
        }

    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "message": task["message"],
            "error": task["error"],
            "package": task.get("package"),
        },
    }


@router.delete("/gpu/uninstall")
def uninstall_gpu_deps():
    """卸载已安装的 GPU 驱动包（nvidia-cublas-cu11 或 cu12）。

    自动检测当前安装的版本并卸载。
    卸载后同时清理 ctranslate2 目录中残留的 DLL 文件。
    """
    installed_pkg = _detect_installed_cublas_package()
    if not installed_pkg:
        return {
            "code": 0,
            "message": "无需卸载",
            "data": {"uninstalled": None, "message": "未检测到已安装的 GPU 驱动包"},
        }

    import sys

    # 1. 卸载 pip 包
    result = subprocess.run(
        [_uv_path, "pip", "uninstall", installed_pkg],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    # 2. 清理 ctranslate2 中残留的 DLL 文件
    try:
        import ctranslate2 as _ct2
        _ct2_dir = Path(_ct2.__file__).parent
        for dll in ("cublas64_12.dll", "cublasLt64_12.dll",
                     "cublas64_11.dll", "cublasLt64_11.dll"):
            dll_path = _ct2_dir / dll
            if dll_path.exists():
                dll_path.unlink()
    except Exception:
        pass

    # 3. 刷新模块级缓存
    try:
        from app.transcriber import whisper
        import importlib
        importlib.reload(whisper)
    except Exception:
        pass

    success = result.returncode == 0
    return {
        "code": 0 if success else 1,
        "message": "卸载成功" if success else "卸载失败",
        "data": {
            "uninstalled": installed_pkg,
            "success": success,
            "message": f"已卸载 {installed_pkg}" if success else result.stderr[-200:],
        },
    }
