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
    import os
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return Path(hf_home) / "hub"


def check_model_downloaded(model_size: str) -> bool:
    """检查指定大小的模型是否已下载到 HF 缓存。

    使用 huggingface_hub.scan_cache_dir 扫描缓存，
    匹配 repo_id 对应的模型。
    """
    repo_id = _MODEL_REPO_MAP.get(model_size)
    if not repo_id:
        return False

    try:
        from huggingface_hub import scan_cache_dir
        cache_info = scan_cache_dir()
        for repo in cache_info.repos:
            if repo.repo_id == repo_id and repo.revisions:
                # 检查是否有实际文件（不只是 refs）
                for rev in repo.revisions:
                    if rev.files and len(rev.files) > 0:
                        return True
    except Exception as e:
        logger.warning(f"扫描 HF 缓存失败: {e}")

    # 回退：手动检查目录
    cache_dir = _get_hf_hub_cache()
    repo_dir_name = repo_id.replace("/", "--")
    if repo_dir_name.startswith("models--"):
        repo_dir_name = repo_dir_name  # already in correct format
    else:
        repo_dir_name = f"models--{repo_dir_name}"
    repo_dir = cache_dir / repo_dir_name
    if repo_dir.exists() and any(repo_dir.rglob("*.bin")):
        return True

    return False


def get_models_status() -> list[dict[str, Any]]:
    """获取所有模型的状态列表。

    Returns:
        [{model_size, downloaded, downloading, failed, error, progress}, ...]
    """
    result: list[dict[str, Any]] = []
    for size in _ALL_MODEL_SIZES:
        ds = _downloads.get(size)
        is_downloading = ds.downloading if ds else False
        # 正在下载时，即使缓存中已有部分文件也不视为"已下载"
        is_downloaded = False if is_downloading else check_model_downloaded(size)

        status: dict[str, Any] = {
            "model_size": size,
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
    is_downloaded = check_model_downloaded(model_size)
    status: dict[str, Any] = {
        "model_size": model_size,
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
