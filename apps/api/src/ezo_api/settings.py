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

    # Files and knowledge (Milestone 2).
    storage_dir: Path = Field(default=API_DIR / "storage", alias="EZO_STORAGE_DIR")
    max_upload_mb: int = Field(default=25, alias="EZO_MAX_UPLOAD_MB")
    vector_store: Literal["auto", "pgvector", "local"] = Field(
        default="auto", alias="EZO_VECTOR_STORE"
    )
    ingestion_mode: Literal["background", "inline"] = Field(
        default="background", alias="EZO_INGESTION_MODE"
    )

    # Research tools.
    web_search_provider: Literal["auto", "anthropic", "tavily", "none"] = Field(
        default="auto", alias="EZO_WEB_SEARCH_PROVIDER"
    )
    web_search_model: str = Field(default="claude-sonnet-5-5", alias="EZO_WEB_SEARCH_MODEL")
    tavily_api_key: SecretStr | None = Field(default=None, alias="TAVILY_API_KEY")
    fetch_allow_private_networks: bool = Field(
        default=False, alias="EZO_FETCH_ALLOW_PRIVATE_NETWORKS"
    )

    # Voice (server-side speech). The browser's speech features stay as fallback.
    voice_providers: Annotated[list[str], NoDecode] = Field(
        default=["auto"], alias="EZO_VOICE_PROVIDERS"
    )
    voicestudio_url: str | None = Field(default=None, alias="VOICESTUDIO_URL")
    voicestudio_api_key: SecretStr | None = Field(default=None, alias="VOICESTUDIO_API_KEY")
    voicestudio_voice: str = Field(default="default", alias="VOICESTUDIO_VOICE")

    # Optional multi-agent orchestration (docs/RUFLO_INTEGRATION_PLAN.md). Native is the
    # default; Ruflo is never required and is off unless explicitly enabled.
    orchestration_provider: Literal["native", "ruflo"] = Field(
        default="native", alias="EZO_ORCHESTRATION_PROVIDER"
    )
    ruflo_enabled: bool = Field(default=False, alias="EZO_RUFLO_ENABLED")
    ruflo_command: str = Field(default="", alias="EZO_RUFLO_COMMAND")
    ruflo_timeout_seconds: float = Field(
        default=600.0, ge=10, le=7200, alias="EZO_RUFLO_TIMEOUT_SECONDS"
    )
    openai_stt_model: str = Field(default="gpt-4o-mini-transcribe", alias="EZO_OPENAI_STT_MODEL")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="EZO_OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="alloy", alias="EZO_OPENAI_TTS_VOICE")
    voice_max_audio_mb: int = Field(default=10, alias="EZO_VOICE_MAX_AUDIO_MB")
    voice_timeout_seconds: float = Field(default=60.0, alias="EZO_VOICE_TIMEOUT_SECONDS")

    # Images (Visual Agent). Exact model IDs are configuration: check your provider's
    # current model list. "none" disables image generation entirely.
    image_providers: Annotated[list[str], NoDecode] = Field(
        default=["auto"], alias="EZO_IMAGE_PROVIDERS"
    )
    openai_image_model: str = Field(default="gpt-image-2", alias="EZO_OPENAI_IMAGE_MODEL")
    gemini_image_model: str = Field(
        default="gemini-2.5-flash-image", alias="EZO_GEMINI_IMAGE_MODEL"
    )
    image_quality: Literal["low", "medium", "high"] = Field(
        default="medium", alias="EZO_IMAGE_QUALITY"
    )
    image_max_per_request: int = Field(default=4, ge=1, le=8, alias="EZO_IMAGE_MAX_PER_REQUEST")
    image_max_per_deck: int = Field(default=4, ge=0, le=20, alias="EZO_IMAGE_MAX_PER_DECK")
    image_timeout_seconds: float = Field(default=120.0, ge=10, le=600, alias="EZO_IMAGE_TIMEOUT")

    # OCR (docs/OCR.md). "auto" uses Tesseract when it is installed; language identifiers
    # must be Tesseract pack names (uzb = Uzbek Latin, uzb_cyrl = Uzbek Cyrillic).
    ocr_provider: Literal["auto", "tesseract", "none"] = Field(
        default="auto", alias="EZO_OCR_PROVIDER"
    )
    tesseract_cmd: str = Field(default="tesseract", alias="EZO_TESSERACT_CMD")
    ocr_languages: Annotated[list[str], NoDecode] = Field(
        default=["uzb", "uzb_cyrl", "rus", "eng"], alias="EZO_OCR_LANGUAGES"
    )
    ocr_timeout_seconds: float = Field(default=60.0, ge=5, le=600, alias="EZO_OCR_TIMEOUT_SECONDS")
    ocr_max_pages: int = Field(default=100, ge=1, le=2000, alias="EZO_OCR_MAX_PAGES")

    # Word/Excel → PDF with LibreOffice (docs/EZO_OFFICE.md). "auto" uses it when installed.
    office_converter: Literal["auto", "none"] = Field(default="auto", alias="EZO_OFFICE_CONVERTER")
    soffice_cmd: str = Field(default="soffice", alias="EZO_SOFFICE_CMD")
    office_convert_timeout_seconds: float = Field(
        default=120.0, ge=10, le=900, alias="EZO_OFFICE_CONVERT_TIMEOUT_SECONDS"
    )

    # Official knowledge sources (docs/OFFICIAL_SOURCES.md). Off unless listed here, after
    # the owner has reviewed the source's terms: e.g. EZO_OFFICIAL_SOURCES=lexuz
    official_sources: Annotated[list[str], NoDecode] = Field(
        default=[], alias="EZO_OFFICIAL_SOURCES"
    )
    official_min_interval_seconds: float = Field(
        default=5.0, ge=1.0, le=600.0, alias="EZO_OFFICIAL_MIN_INTERVAL_SECONDS"
    )
    official_max_documents_per_run: int = Field(
        default=25, ge=1, le=500, alias="EZO_OFFICIAL_MAX_DOCUMENTS_PER_RUN"
    )
    official_max_retry_after_seconds: float = Field(
        default=120.0, ge=0, le=3600, alias="EZO_OFFICIAL_MAX_RETRY_AFTER_SECONDS"
    )

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "api_token",
        "tavily_api_key",
        "voicestudio_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("preferred_provider", "openai_base_url", "voicestudio_url", mode="before")
    @classmethod
    def _blank_str_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("storage_dir", mode="before")
    @classmethod
    def _blank_storage_is_default(cls, value: object) -> object:
        # `EZO_STORAGE_DIR=` (empty, as in .env.example) must not mean "current folder".
        if value is None or (isinstance(value, str) and not value.strip()):
            return API_DIR / "storage"
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("voice_providers", mode="before")
    @classmethod
    def _split_voice_providers(cls, value: object) -> object:
        if isinstance(value, str):
            names = [name.strip().lower() for name in value.split(",") if name.strip()]
            return names or ["auto"]
        return value

    @field_validator("official_sources", mode="before")
    @classmethod
    def _split_official_sources(cls, value: object) -> object:
        if isinstance(value, str):
            return [name.strip().lower() for name in value.split(",") if name.strip()]
        return value

    @field_validator("ocr_languages", mode="before")
    @classmethod
    def _split_ocr_languages(cls, value: object) -> object:
        if isinstance(value, str):
            names = [n.strip() for n in value.replace("+", ",").split(",") if n.strip()]
            return names or ["uzb", "uzb_cyrl", "rus", "eng"]
        return value

    @field_validator("image_providers", mode="before")
    @classmethod
    def _split_image_providers(cls, value: object) -> object:
        if isinstance(value, str):
            names = [name.strip().lower() for name in value.split(",") if name.strip()]
            return names or ["auto"]
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
