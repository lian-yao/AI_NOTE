"""
System health API.
"""
import time
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
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


class ConfigUpdate(BaseModel):
    llm_provider: str | None = None
    transcriber_mode: str | None = None
    retrieval_top_k: int | None = None
    whisper_model_size: str | None = None
    whisper_device: str | None = None


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
    try:
        disk = shutil.disk_usage(settings.data_dir)
        storage_usage = disk.total - disk.free
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



_EMBEDDING_CONFIG_PATH: _Path | None = None

def _get_embedding_config_path() -> _Path:
    global _EMBEDDING_CONFIG_PATH
    if _EMBEDDING_CONFIG_PATH is None:
        _EMBEDDING_CONFIG_PATH = _Path(settings.data_dir) / "embedding_config.json"
    return _EMBEDDING_CONFIG_PATH


@router.get("/embedding-model")
def get_embedding_model_config():
    """获取嵌入模型配置。"""
    p = _get_embedding_config_path()
    if p.exists():
        try:
            return {"model": json.loads(p.read_text(encoding="utf-8")).get("model", "text-embedding-v3")}
        except:
            pass
    return {"model": "text-embedding-v3"}


@router.put("/embedding-model")
def set_embedding_model_config(body: dict):
    """设置嵌入模型配置。"""
    model = (body.get("model") or "text-embedding-v3").strip()
    p = _get_embedding_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": model}), encoding="utf-8")
    return {"model": model, "saved": True}

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


def _detect_cublas_installed() -> bool:
    """检测 nvidia-cublas-cuXX 是否已安装且版本与 CUDA 驱动匹配。"""
    installed_pkg = _detect_installed_cublas_package()
    if not installed_pkg:
        return False

    # 获取 CUDA 驱动版本，检查与已安装包的匹配
    cuda_version, _ = _detect_cuda_version()
    recommended = _get_recommended_package(cuda_version)

    # 版本不匹配：驱动是 11.x 但装的是 cu12（或反过来）
    if recommended and recommended != installed_pkg:
        return False

    # 检查 DLL 是否可被 ctranslate2 加载
    try:
        from app.transcriber.whisper import _HAS_CUDA_DLLS
        return _HAS_CUDA_DLLS
    except Exception:
        pass

    # 回退：直接检查 DLL 文件
    try:
        import ctranslate2 as _ct2
        _ct2_dir = Path(_ct2.__file__).parent
        for dll in ("cublas64_12.dll", "cublas64_11.dll"):
            if (_ct2_dir / dll).exists():
                return True
        import nvidia.cublas
        return True
    except (ImportError, Exception):
        return False


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
    installed_package = _detect_installed_cublas_package()
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