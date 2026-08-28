"""Configuration. Every value comes from the shared .env so this service and the
existing osw-agent stack stay credential-compatible."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Postgres -----------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "osw_observability"
    postgres_user: str = "osw"
    postgres_password: str = ""
    postgres_pool_max: int = 25
    # "prefer" tries SSL first and falls back to plain if the server doesn't
    # offer it -- works unmodified against the local docker-compose Postgres
    # (no SSL configured) and against a managed one that requires it (Render,
    # Neon, ...), which otherwise refuses a plain connection outright.
    postgres_sslmode: str = "prefer"

    # --- Kore.ai (reused from the existing stack) ---------------------------
    kore_host: str = "https://bots.kore.ai"

    # --- Zendesk ------------------------------------------------------------
    zendesk_subdomain: str = ""
    zendesk_email: str = ""
    zendesk_api_token: str = ""

    # --- Claude via OpenRouter ---------------------------------------------
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-5"

    # --- This service -------------------------------------------------------
    osw_data_root: Path = Field(default=Path("/data"))
    default_bot_id: str = "marina"
    app_version: str = "1.0.0"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password} sslmode={self.postgres_sslmode}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
