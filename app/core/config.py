"""
系统配置管理
优先级：环境变量 > .env > config.yaml > 默认值
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.paths import project_root

_default_data_dir = str(project_root() / "data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VN_",
    )

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # LLM
    tongyi_api_key: str = ""
    deepseek_api_key: str = ""
    llm_provider: str = "tongyi"

    # Transcribe
    bjian_app_id: str = ""
    bjian_access_token: str = ""
    whisper_model_size: str = "medium"
    whisper_device: str = "auto"

    # Storage
    data_dir: str = _default_data_dir
    video_retention: str = "processed"

    # Retrieval
    retrieval_top_k: int = 5
    rrf_k: int = 60


settings = Settings()
