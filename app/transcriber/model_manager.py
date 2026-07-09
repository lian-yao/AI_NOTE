"""
Whisper 模型管理器：模型发现、下载、状态追踪。

负责：
- 扫描 HF 缓存中已下载的 faster-whisper 模型
- 启动模型下载（后台线程 + 进度追踪）
- 查询下载状态

模型来源：
- faster-whisper: Systran/faster-whisper-{size}
- faster-whisper turbo: mobiuslabsgmbh/faster-whisper-large-v3-turbo
"""
from __future__ import annotations

import threading
import time
import shutil
import os
from pathlib import Path
from typing import Any

from loguru import logger

# ── 模型大小 → HuggingFace repo_id 映射 ──
_MODEL_REPO_MAP: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

# Approximate download/cache sizes. Hugging Face revisions can vary slightly,
# so the UI labels these as estimates and shows actual disk usage when cached.
_MODEL_ESTIMATED_SIZE_MB: dict[str, int] = {
    "tiny": 75,
    "base": 145,
    "small": 466,
    "medium": 1500,
    "large-v3": 3100,
    "turbo": 1600,
}

_MODEL_WEIGHT_SUFFIXES = (".bin", ".safetensors")

# ── 所有已知的模型大小 ──
_ALL_MODEL_SIZES: list[str] = ["tiny", "base", "small", "medium", "large-v3", "turbo"]

# ── 下载状态 ──
class DownloadStatus:
    """单个模型的下载状态。"""
    def __init__(self):
        self.downloading: bool = False
        self.progress: float = 0.0       # 0.0 ~ 100.0
        self.message: str = ""
        self.failed: bool = False
        self.error: str | None = None
        self.started_at: float | None = None
        self.completed_at: float | None = None

# 全局下载状态字典：key = model_size
_downloads: dict[str, DownloadStatus] = {}


def _get_hf_hub_cache() -> Path:
    """获取 HuggingFace Hub 缓存目录。"""
    hub_cache = (
        os.environ.get("HF_HUB_CACHE")
        or os.environ.get("HUGGINGFACE_HUB_CACHE")
    )
    if hub_cache:
        return Path(hub_cache).expanduser()
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return Path(hf_home).expanduser() / "hub"


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.expanduser())
    return result


def _get_hf_hub_caches() -> list[Path]:
    """Return all HuggingFace hub cache roots worth scanning.

    The desktop app sets HF_HOME to its AppData runtime directory, but users may
    already have faster-whisper models in the default user cache from web/dev
    runs. Scanning both prevents already downloaded models from looking missing.
    """
    candidates: list[Path] = [_get_hf_hub_cache()]

    for env_name in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value).expanduser())

    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        candidates.append(Path(hf_home).expanduser() / "hub")

    candidates.append(Path.home() / ".cache" / "huggingface" / "hub")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "huggingface" / "hub")

    return _dedupe_paths(candidates)


def _format_estimated_size(model_size: str) -> str | None:
    size_mb = _MODEL_ESTIMATED_SIZE_MB.get(model_size)
    if not size_mb:
        return None
    if size_mb >= 1024:
        return f"约 {size_mb / 1024:.1f} GB"
    return f"约 {size_mb} MB"


def _repo_cache_dir(repo_id: str, hub_cache: Path | None = None) -> Path:
    repo_dir_name = repo_id.replace("/", "--")
    if not repo_dir_name.startswith("models--"):
        repo_dir_name = f"models--{repo_dir_name}"
    return (hub_cache or _get_hf_hub_cache()) / repo_dir_name


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _is_model_weight_name(name: str) -> bool:
    lower = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if lower.endswith(".incomplete"):
        return False
    return lower.endswith(_MODEL_WEIGHT_SUFFIXES)


def _cache_entry(
    *,
    downloaded: bool,
    repo_path: Path,
    downloaded_size_bytes: int | None = None,
) -> dict[str, Any]:
    cache_size = _dir_size(repo_path) if repo_path.exists() else 0
    partial = bool(cache_size and not downloaded)
    return {
        "downloaded": downloaded,
        "downloaded_size_bytes": downloaded_size_bytes if downloaded else None,
        "cache_size_bytes": cache_size or downloaded_size_bytes,
        "partial": partial,
        "partial_size_bytes": cache_size if partial else None,
        "cache_path": str(repo_path),
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _merge_cache_entry(
    found: dict[str, dict[str, Any]],
    model_size: str,
    entry: dict[str, Any],
) -> None:
    current = found.get(model_size)
    if current is None:
        found[model_size] = entry
        return
    if entry.get("downloaded") and not current.get("downloaded"):
        found[model_size] = entry
        return
    if entry.get("downloaded") == current.get("downloaded"):
        entry_size = int(entry.get("cache_size_bytes") or entry.get("downloaded_size_bytes") or 0)
        current_size = int(current.get("cache_size_bytes") or current.get("downloaded_size_bytes") or 0)
        if entry_size > current_size:
            found[model_size] = entry


def scan_whisper_cache() -> dict[str, dict[str, Any]]:
    """Scan HuggingFace cache once and return downloaded Whisper models."""
    repo_to_size = {repo_id: size for size, repo_id in _MODEL_REPO_MAP.items()}
    found: dict[str, dict[str, Any]] = {}

    try:
        from huggingface_hub import scan_cache_dir

        for hub_cache in _get_hf_hub_caches():
            if not hub_cache.exists():
                continue
            try:
                cache_info = scan_cache_dir(cache_dir=hub_cache)
            except Exception as e:
                logger.warning(f"扫描 HF 缓存失败 {hub_cache}: {e}")
                continue

            for repo in cache_info.repos:
                model_size = repo_to_size.get(repo.repo_id)
                if not model_size or not repo.revisions:
                    continue

                has_model_weights = any(
                    _is_model_weight_name(str(getattr(file, "file_name", "")))
                    for rev in repo.revisions
                    for file in rev.files
                )

                size_on_disk = getattr(repo, "size_on_disk", None)
                if size_on_disk is None:
                    size_on_disk = sum(
                        int(getattr(rev, "size_on_disk", 0) or 0)
                        for rev in repo.revisions
                    )

                repo_path = getattr(repo, "repo_path", None)
                if not repo_path:
                    repo_path = _repo_cache_dir(repo.repo_id, hub_cache)
                _merge_cache_entry(
                    found,
                    model_size,
                    _cache_entry(
                        downloaded=has_model_weights,
                        downloaded_size_bytes=size_on_disk or None,
                        repo_path=Path(repo_path),
                    ),
                )
    except Exception as e:
        logger.warning(f"扫描 HF 缓存失败: {e}")

    # Fallback/manual pass covers older huggingface_hub versions and custom HF_HOME layouts.
    for model_size, repo_id in _MODEL_REPO_MAP.items():
        repo_dirs = [
            _repo_cache_dir(repo_id, hub_cache)
            for hub_cache in _get_hf_hub_caches()
        ]
        existing_repo_dirs = [repo_dir for repo_dir in repo_dirs if repo_dir.exists()]
        if not existing_repo_dirs:
            continue

        for repo_dir in existing_repo_dirs:
            has_model_file = any(
                path.is_file() and _is_model_weight_name(path.name)
                for path in repo_dir.rglob("*")
            )
            cache_size = _dir_size(repo_dir)
            if not has_model_file and cache_size <= 0:
                continue

            _merge_cache_entry(
                found,
                model_size,
                _cache_entry(
                    downloaded=has_model_file,
                    downloaded_size_bytes=cache_size if has_model_file else None,
                    repo_path=repo_dir,
                ),
            )

    return found


def check_model_downloaded(model_size: str) -> bool:
    """检查指定大小的模型是否已下载到 HF 缓存。

    使用 huggingface_hub.scan_cache_dir 扫描缓存，
    匹配 repo_id 对应的模型。
    """
    return bool(scan_whisper_cache().get(model_size, {}).get("downloaded"))


def get_models_status() -> list[dict[str, Any]]:
    """获取所有模型的状态列表。

    Returns:
        [{model_size, downloaded, downloading, failed, error, progress}, ...]
    """
    result: list[dict[str, Any]] = []
    cached_models = scan_whisper_cache()
    for size in _ALL_MODEL_SIZES:
        ds = _downloads.get(size)
        is_downloading = ds.downloading if ds else False
        # 正在下载时，即使缓存中已有部分文件也不视为"已下载"
        cache_info = cached_models.get(size, {})
        is_downloaded = False if is_downloading else bool(cache_info.get("downloaded"))

        status: dict[str, Any] = {
            "model_size": size,
            "repo_id": _MODEL_REPO_MAP.get(size),
            "estimated_size_mb": _MODEL_ESTIMATED_SIZE_MB.get(size),
            "estimated_size_label": _format_estimated_size(size),
            "downloaded_size_bytes": cache_info.get("downloaded_size_bytes"),
            "cache_size_bytes": cache_info.get("cache_size_bytes"),
            "partial_size_bytes": cache_info.get("partial_size_bytes"),
            "cache_path": cache_info.get("cache_path"),
            "partial": bool(cache_info.get("partial")),
            "downloaded": is_downloaded,
            "downloading": is_downloading,
            "failed": ds.failed if ds else False,
            "error": ds.error if ds else None,
        }
        if ds and ds.downloading:
            status["progress"] = ds.progress
        result.append(status)
    return result


def get_model_status(model_size: str) -> dict[str, Any] | None:
    """获取单个模型的状态。"""
    if model_size not in _ALL_MODEL_SIZES:
        return None
    ds = _downloads.get(model_size)
    cache_info = scan_whisper_cache().get(model_size, {})
    is_downloaded = bool(cache_info.get("downloaded"))
    status: dict[str, Any] = {
        "model_size": model_size,
        "repo_id": _MODEL_REPO_MAP.get(model_size),
        "estimated_size_mb": _MODEL_ESTIMATED_SIZE_MB.get(model_size),
        "estimated_size_label": _format_estimated_size(model_size),
        "downloaded_size_bytes": cache_info.get("downloaded_size_bytes"),
        "cache_size_bytes": cache_info.get("cache_size_bytes"),
        "partial_size_bytes": cache_info.get("partial_size_bytes"),
        "cache_path": cache_info.get("cache_path"),
        "partial": bool(cache_info.get("partial")),
        "downloaded": is_downloaded,
        "downloading": ds.downloading if ds else False,
        "failed": ds.failed if ds else False,
        "error": ds.error if ds else None,
    }
    if ds and ds.downloading:
        status["progress"] = ds.progress
    return status


def get_download_progress(model_size: str) -> dict[str, Any] | None:
    """获取模型下载进度（供轮询）。"""
    ds = _downloads.get(model_size)
    if not ds:
        return None
    return {
        "model_size": model_size,
        "downloading": ds.downloading,
        "progress": ds.progress,
        "message": ds.message,
        "failed": ds.failed,
        "error": ds.error,
        "elapsed_seconds": (time.time() - ds.started_at) if ds.started_at else 0,
    }


def delete_model_cache(model_size: str) -> dict[str, Any]:
    """删除指定 Whisper 模型的 HuggingFace 本地缓存。"""
    if model_size not in _MODEL_REPO_MAP:
        return {
            "status": "error",
            "model_size": model_size,
            "message": f"未知的模型大小: {model_size}",
        }

    ds = _downloads.get(model_size)
    if ds and ds.downloading:
        return {
            "status": "downloading",
            "model_size": model_size,
            "message": f"模型 {model_size} 正在下载中，不能删除缓存",
        }

    cache_info = scan_whisper_cache().get(model_size, {})
    cache_path_value = cache_info.get("cache_path")
    cache_path = Path(cache_path_value) if cache_path_value else _repo_cache_dir(_MODEL_REPO_MAP[model_size])
    hub_caches = _get_hf_hub_caches()

    if not cache_path.exists():
        return {
            "status": "not_found",
            "model_size": model_size,
            "deleted": False,
            "freed_bytes": 0,
            "message": f"模型 {model_size} 未找到本地缓存",
        }

    if (
        cache_path.is_symlink()
        or not cache_path.is_dir()
        or not any(_is_relative_to(cache_path, hub_cache) for hub_cache in hub_caches)
    ):
        return {
            "status": "error",
            "model_size": model_size,
            "deleted": False,
            "freed_bytes": 0,
            "cache_path": str(cache_path),
            "message": f"缓存路径不安全，已拒绝删除: {cache_path}",
        }

    expected_dirs = {
        _repo_cache_dir(_MODEL_REPO_MAP[model_size], hub_cache).resolve()
        for hub_cache in hub_caches
    }
    try:
        resolved_cache_path = cache_path.resolve()
    except OSError:
        resolved_cache_path = cache_path
    if resolved_cache_path not in expected_dirs:
        return {
            "status": "error",
            "model_size": model_size,
            "deleted": False,
            "freed_bytes": 0,
            "cache_path": str(cache_path),
            "message": f"缓存路径与模型仓库不匹配，已拒绝删除: {cache_path}",
        }

    freed = _dir_size(cache_path)
    try:
        shutil.rmtree(cache_path)
    except OSError as exc:
        logger.warning(f"删除模型缓存失败 {model_size}: {exc}")
        return {
            "status": "error",
            "model_size": model_size,
            "deleted": False,
            "freed_bytes": 0,
            "cache_path": str(cache_path),
            "message": f"删除模型缓存失败: {exc}",
        }

    _downloads.pop(model_size, None)
    logger.info(f"已删除模型缓存: {model_size} path={cache_path} freed={freed}")
    return {
        "status": "deleted",
        "model_size": model_size,
        "deleted": True,
        "freed_bytes": freed,
        "cache_path": str(cache_path),
        "message": f"已删除模型 {model_size} 的本地缓存",
    }


def start_download(model_size: str) -> dict[str, Any]:
    """启动模型下载（后台线程）。

    Args:
        model_size: 模型大小 (tiny/base/small/medium/large-v3/turbo)

    Returns:
        {"status": "started" | "already_downloading" | "already_downloaded",
         "model_size": str, "message": str}
    """
    if model_size not in _MODEL_REPO_MAP:
        return {"status": "error", "model_size": model_size,
                "message": f"未知的模型大小: {model_size}"}

    if check_model_downloaded(model_size):
        return {"status": "already_downloaded", "model_size": model_size,
                "message": f"模型 {model_size} 已下载"}

    ds = _downloads.get(model_size)
    if ds and ds.downloading:
        return {"status": "already_downloading", "model_size": model_size,
                "message": f"模型 {model_size} 正在下载中", "progress": ds.progress}

    # 创建下载状态
    ds = DownloadStatus()
    ds.downloading = True
    ds.started_at = time.time()
    ds.message = "准备下载..."
    _downloads[model_size] = ds

    repo_id = _MODEL_REPO_MAP[model_size]

    def _download_worker():
        try:
            from huggingface_hub import hf_hub_download, list_repo_files, snapshot_download

            ds.message = f"正在连接 HuggingFace，获取 {model_size} 模型文件列表..."
            ds.progress = 3.0
            logger.info(f"开始下载模型: {repo_id}")

            # 尝试获取文件列表（需要网络访问 HF API）
            try:
                all_files = list_repo_files(repo_id)
                model_files = [f for f in all_files if not f.startswith(".")]
                total_files = len(model_files)
                use_per_file_progress = True
            except Exception as e:
                logger.warning(f"无法获取文件列表，回退到 snapshot_download: {e}")
                model_files = []
                total_files = 0
                use_per_file_progress = False

            if use_per_file_progress and total_files > 0:
                # ── 逐文件下载，精确实时进度 ──
                ds.message = f"模型 {model_size} 共 {total_files} 个文件，开始下载..."
                for idx, filename in enumerate(model_files):
                    file_pct_start = 5.0 + (idx / total_files) * 90.0
                    ds.progress = round(file_pct_start, 1)
                    ds.message = f"下载中 ({idx + 1}/{total_files}): {filename}"

                    hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        resume_download=True,
                    )

                    file_pct_end = 5.0 + ((idx + 1) / total_files) * 90.0
                    ds.progress = round(file_pct_end, 1)
            else:
                # ── 回退：snapshot_download 粗粒度进度 ──
                ds.progress = 10.0
                ds.message = f"正在下载 {model_size} 模型（粗粒度进度）..."

                snapshot_download(
                    repo_id=repo_id,
                    resume_download=True,
                    max_workers=4,
                )

                ds.progress = 95.0

            ds.progress = 100.0
            ds.downloading = False
            ds.completed_at = time.time()
            ds.message = f"模型 {model_size} 下载完成"
            logger.info(f"模型下载完成: {repo_id}")

        except Exception as e:
            ds.downloading = False
            ds.failed = True
            ds.error = str(e)
            ds.message = f"下载失败: {e}"
            ds.progress = 0.0
            logger.error(f"模型下载失败 {repo_id}: {e}")

    thread = threading.Thread(target=_download_worker, daemon=True, name=f"whisper-dl-{model_size}")
    thread.start()

    return {"status": "started", "model_size": model_size,
            "message": f"模型 {model_size} 下载已启动"}


def reset_download(model_size: str) -> bool:
    """重置下载状态（用于重试失败的任务）。"""
    if model_size in _downloads:
        ds = _downloads[model_size]
        if not ds.downloading:
            del _downloads[model_size]
            return True
    return False
