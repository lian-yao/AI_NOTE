"""
系统配置管理
优先级：环境变量 > .env > config.yaml > 默认值
"""
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.paths import project_root

_default_data_dir = str(project_root() / "data")

# 加载 .env 所有变量到系统环境（包括非 VN_ 前缀的，如 HF_ENDPOINT）
load_dotenv(project_root() / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="VN_",
    )

    # Database
    database_url: str = "sqlite:///" + str(project_root() / "data" / "app.db")

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
    vector_db_path: str = "./data/chromadb"

    # Transcribe
    bjian_app_id: str = ""
    bjian_access_token: str = ""
    whisper_model_size: str = "medium"
    whisper_device: str = "auto"

    # Platform cookies
    # 来源: "browser"（推荐，从浏览器加密存储直接读取）/ "file"（明文 cookies.txt）/ "none"
    bilibili_cookie_source: str = "browser"
    # 当 source="browser" 时指定浏览器: chrome / firefox / edge / brave / opera / chromium
    bilibili_cookie_browser: str = "chrome"
    # 当 source="file" 时指定 cookies.txt 路径（相对路径相对于项目根目录）
    bilibili_cookie_file: str = "data/cookies.txt"

    # Storage
    data_dir: str = _default_data_dir
    video_retention: str = "processed"

    # Retrieval
    retrieval_top_k: int = 5
    rrf_k: int = 60


settings = Settings()
