"""
项目路径工具。
提供获取项目根目录、相对路径、绝对路径的统一接口。
"""
from __future__ import annotations
from pathlib import Path

_PROJECT_ROOT: Path | None = None

def project_root() -> Path:
    """返回项目根目录的绝对路径。"""
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    return _PROJECT_ROOT

def project_path(*parts: str) -> Path:
    """返回项目根目录下指定路径的绝对路径。

    Usage:
        project_path("data", "logs") -> /abs/root/data/logs
    """
    return project_root().joinpath(*parts)

def relative_path(path: str | Path) -> Path:
    """将任意路径解析为相对于项目根目录的路径。

    Usage:
        relative_path("/data/logs") -> data/logs
    """
    return Path(path).resolve().relative_to(project_root())
