"""Application settings.

All configuration comes from environment variables (or a `.env` file in the
repository root). Secrets are never hardcoded: see `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[2]
"""The `apps/api` directory (or `/app` inside Docker)."""


def _env_files() -> tuple[Path, ...]:
    """`.env` in the repository root first, then `apps/api/.env` (later wins)."""
    candidates = [API_DIR / ".env"]
    if len(API_DIR.parents) >= 2:
        candidates.insert(0, API_DIR.parents[1] / ".env")
    return tuple(candidates)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production", "test"] = Field(
        default="development", alias="EZO_ENV"
    )
    log_level: str = Field(default="INFO", alias="EZO_LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+psycopg://ezo:ezo@localhost:5432/ezo", alias="DATABASE_URL"
    )

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"], alias="EZO_CORS_ORIGINS"
    )

    # Authentication (see ezo_api/auth).
    auth_mode: Literal["local", "token"] = Field(default="local", alias="EZO_AUTH_MODE")
    api_token: SecretStr | None = Field(default=None, alias="EZO_API_TOKEN")
    owner_email: str = Field(default="owner@ezo.local", alias="EZO_OWNER_EMAIL")
    owner_name: str = Field(default="Owner", alias="EZO_OWNER_NAME")

    # Model providers. Leave empty to disable a provider.
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    preferred_provider: Literal["openai", "anthropic", "gemini"] | None = Field(
        default=None, alias="EZO_PREFERRED_PROVIDER"
    )
    provider_timeout_seconds: float = Field(default=120.0, alias="EZO_PROVIDER_TIMEOUT")

    models_config_path: Path = Field(
        default=API_DIR / "config" / "models.toml", alias="EZO_MODELS_CONFIG"
    )
    personality_config_path: Path = Field(
        default=API_DIR / "config" / "personality.toml", alias="EZO_PERSONALITY_CONFIG"
    )

    # Limits and safety.
    rate_limit_chat_per_minute: int = Field(default=30, alias="EZO_RATE_LIMIT_CHAT")
    rate_limit_default_per_minute: int = Field(default=240, alias="EZO_RATE_LIMIT_DEFAULT")
    max_message_chars: int = Field(default=16_000, alias="EZO_MAX_MESSAGE_CHARS")
    context_message_limit: int = Field(default=30, alias="EZO_CONTEXT_MESSAGES")
    context_char_budget: int = Field(default=60_000, alias="EZO_CONTEXT_CHARS")

    timezone: str = Field(default="Asia/Tashkent", alias="EZO_TIMEZONE")
    expose_debug_traces: bool = Field(default=True, alias="EZO_DEBUG_TRACES")

    @field_validator(
        "openai_api_key", "anthropic_api_key", "gemini_api_key", "api_token", mode="before"
    )
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("preferred_provider", "openai_base_url", mode="before")
    @classmethod
    def _blank_str_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
