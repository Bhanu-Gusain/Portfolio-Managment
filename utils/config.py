"""Central config loader. Fail loud if required vars missing."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = "data/analysis.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120
    cache_max_age_hours: int = 12
    log_level: str = "INFO"

    @property
    def db_abspath(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
