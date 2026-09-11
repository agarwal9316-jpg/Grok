"""Application configuration from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    database_url: str = "sqlite:///./grok_org_os.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # Workspace sandbox for fs_* tools / file connector
    workspace_dir: str = "workspace"

    # SMTP email connector (optional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Google connector stubs (activate when set)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # Generic REST connector defaults
    rest_base_url: str = ""
    rest_api_token: str = ""

    # Webhook outbound
    webhook_url: str = ""

    @property
    def has_llm_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    def workspace_path(self) -> Path:
        p = Path(self.workspace_dir)
        if not p.is_absolute():
            p = Path.cwd() / p
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
