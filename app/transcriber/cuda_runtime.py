from __future__ import annotations

import os
import sys
from pathlib import Path

CUDA_DLL_SETS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("nvidia-cublas-cu12", ("cublas64_12.dll", "cublasLt64_12.dll")),
    ("nvidia-cublas-cu11", ("cublas64_11.dll", "cublasLt64_11.dll")),
)

_DLL_DIRECTORY_HANDLES: list[object] = []
_ACTIVATED_DLL_DIRS: set[str] = set()


def gpu_python_packages_dir() -> Path:
    """Directory used by the desktop sidecar for optional GPU packages."""
    base = os.environ.get("VN_APP_DATA_DIR")
    if base:
        return Path(base) / "python-packages"
    return Path.cwd() / "data" / "python-packages"


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if not path:
            continue
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.expanduser())
    return result


def iter_python_site_package_dirs() -> list[Path]:
    candidates: list[Path] = [gpu_python_packages_dir()]

    for item in sys.path:
        if item:
            candidates.append(Path(item))

    for item in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if item:
            candidates.append(Path(item))

    try:
        import site

        for item in site.getsitepackages():
            candidates.append(Path(item))
        user_site = site.getusersitepackages()
        if user_site:
            candidates.append(Path(user_site))
    except Exception:
        pass

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(Path(conda_prefix) / "Lib" / "site-packages")

    try:
        project_root = Path(__file__).resolve().parents[2]
        candidates.extend(
            [
                project_root / ".venv" / "Lib" / "site-packages",
                project_root / ".venv" / "lib" / "site-packages",
            ]
        )
    except Exception:
        pass

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.extend(
                Path(local_app_data).glob(
                    "Programs/Python/Python*/Lib/site-packages"
                )
            )
        app_data = os.environ.get("APPDATA")
        if app_data:
            candidates.extend(Path(app_data).glob("Python/Python*/site-packages"))

    return [path for path in _dedupe_paths(candidates) if path.exists()]


def iter_cuda_dll_dirs() -> list[Path]:
    candidates: list[Path] = []

    for site_dir in iter_python_site_package_dirs():
        candidates.extend(
            [
                site_dir / "nvidia" / "cublas" / "bin",
                site_dir / "ctranslate2",
            ]
        )

    for env_name in ("CUDA_PATH", "CUDA_HOME"):
        cuda_root = os.environ.get(env_name)
        if cuda_root:
            candidates.append(Path(cuda_root) / "bin")

    if sys.platform == "win32":
        for item in os.environ.get("PATH", "").split(os.pathsep):
            if item:
                candidates.append(Path(item))

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(
                Path(local_app_data) / "Programs" / "Ollama" / "lib" / "ollama" / "cuda_v12"
            )

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            root = Path(meipass)
            candidates.extend(
                [
                    root,
                    root / "nvidia" / "cublas" / "bin",
                    root / "_internal" / "nvidia" / "cublas" / "bin",
                    root / "ctranslate2",
                ]
            )

    return [path for path in _dedupe_paths(candidates) if path.exists()]


def cublas_package_from_dir(path: Path) -> str | None:
    for package, dlls in CUDA_DLL_SETS:
        if all((path / dll).exists() for dll in dlls):
            return package
    return None


def detect_cublas_dll_package() -> str | None:
    for path in iter_cuda_dll_dirs():
        package = cublas_package_from_dir(path)
        if package:
            return package
    return None


def activate_cuda_dll_dir(path: Path) -> None:
    try:
        key = str(path.resolve())
    except OSError:
        key = str(path)
    if key in _ACTIVATED_DLL_DIRS:
        return
    _ACTIVATED_DLL_DIRS.add(key)

    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(key))
        except OSError:
            pass

    current_path = os.environ.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if key not in parts:
        os.environ["PATH"] = key + (os.pathsep + current_path if current_path else "")


def ensure_cuda_dlls_available() -> bool:
    if sys.platform != "win32":
        return True

    try:
        import ctranslate2 as ct2

        ct2_dir = Path(ct2.__file__).parent
    except Exception:
        return False

    if cublas_package_from_dir(ct2_dir):
        activate_cuda_dll_dir(ct2_dir)
        return True

    for dll_dir in iter_cuda_dll_dirs():
        if cublas_package_from_dir(dll_dir):
            activate_cuda_dll_dir(dll_dir)
            return True

    return False
