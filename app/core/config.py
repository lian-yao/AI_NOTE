"""
系统配置管理
优先级：环境变量 > .env > config.yaml > 默认值
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.paths import project_root

# 加载 .env 所有变量到系统环境（包括非 VN_ 前缀的，如 HF_ENDPOINT）。
# 需要在计算默认数据目录前加载，这样 VN_APP_DATA_DIR / VN_DATA_DIR 能参与默认值选择。
load_dotenv(project_root() / ".env")


def _configured_app_data_dir() -> Path:
    raw = os.environ.get("VN_APP_DATA_DIR", "").strip()
    if not raw:
        return project_root() / "data"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path


_app_data_dir = _configured_app_data_dir()
_storage_config_file = _app_data_dir / "storage_config.json"


def app_data_dir() -> Path:
    return _app_data_dir


def storage_config_file() -> Path:
    return _storage_config_file


def _configured_data_dir() -> str | None:
    if not _storage_config_file.exists():
        return None
    try:
        data = json.loads(_storage_config_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    raw = str(data.get("dataRootPath") or "").strip()
    if not raw:
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return str(path)


_default_data_dir = _configured_data_dir() or str(_app_data_dir)
_default_data_path = Path(_default_data_dir)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="VN_",
    )

    # Database
    database_url: str = "sqlite:///" + str(_default_data_path / "app.db")

    # LLM
    tongyi_api_key: str = ""
    deepseek_api_key: str = ""
    llm_provider: str = "tongyi"
    tongyi_model: str = "qwen-plus"
    deepseek_model: str = "deepseek-chat"

    # Embedding（向量化）
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v3"

    # Vector DB（向量数据库）
    vector_db_path: str = str(_default_data_path / "chromadb")

    # Transcribe
    bjian_app_id: str = ""
    bjian_access_token: str = ""
    whisper_model_size: str = "medium"
    whisper_device: str = "auto"

    # Platform cookies
    # 来源: "string"（设置页粘贴）/ "browser"（从浏览器读取）/ "file"（cookies.txt）/ "none"
    # 默认不读浏览器 Cookie，避免 Windows DPAPI/浏览器锁库导致解析流程 500。
    bilibili_cookie_source: str = "string"
    # 仅当 source="browser" 时指定浏览器: chrome / firefox / edge / brave / opera / chromium
    bilibili_cookie_browser: str = "chrome"
    # 当 source="file" 时指定 cookies.txt 路径（相对路径相对于项目根目录）
    bilibili_cookie_file: str = str(_default_data_path / "cookies.txt")

    # Storage
    data_dir: str = _default_data_dir
    video_retention: str = "processed"

    # Retrieval
    retrieval_top_k: int = 5
    rrf_k: int = 60


settings = Settings()
