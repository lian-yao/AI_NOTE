"""
文件管理工具：目录结构创建、产物清理、磁盘空间检查。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def ensure_video_dir(video_id: str, base_dir: str = "./data") -> Path:
    """创建视频产物目录。

    Returns:
        data/videos/{video_id}/ 的 Path 对象
    """
    video_dir = Path(base_dir) / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    return video_dir


def save_meta_json(video_dir: Path, meta: dict) -> Path:
    """将视频元数据保存为 meta.json。"""
    meta_path = video_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def load_meta_json(video_dir: Path) -> dict:
    """从 meta.json 读取视频元数据。"""
    meta_path = video_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json 不存在: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def clean_artifacts(video_dir: Path, keep: list[str] | None = None) -> int:
    """清理视频产物目录中的文件。

    Args:
        video_dir: 产物目录
        keep: 保留的文件名列表（如 ["note.md"]），None 表示删除整个目录

    Returns:
        释放的字节数
    """
    if not video_dir.exists():
        return 0

    if keep is None:
        # 删除整个目录
        size = _dir_size(video_dir)
        shutil.rmtree(video_dir, ignore_errors=True)
        return size

    freed = 0
    keep_set = set(keep)
    for item in list(video_dir.iterdir()):
        if item.name not in keep_set:
            if item.is_file():
                freed += item.stat().st_size
                item.unlink()
            elif item.is_dir():
                freed += _dir_size(item)
                shutil.rmtree(item, ignore_errors=True)
    return freed


def check_disk_space(video_dir: Path, required_bytes: int) -> bool:
    """检查磁盘剩余空间是否足够。

    Args:
        video_dir: 用于判断所在磁盘分区的目录
        required_bytes: 需要的字节数

    Returns:
        True 表示空间足够
    """
    try:
        usage = shutil.disk_usage(video_dir)
        return usage.free >= required_bytes
    except Exception:
        return True  # 无法检查时默认放行


def _dir_size(path: Path) -> int:
    """递归计算目录大小（字节）。"""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception:
        pass
    return total
