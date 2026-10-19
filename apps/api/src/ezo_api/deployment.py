"""Single-owner production startup policy and logging; independent of agent logic."""

from __future__ import annotations

import logging
import tempfile
from types import TracebackType
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import SecretStr

from ezo_api.settings import Settings


class DeploymentError(RuntimeError):
    """Unsafe or incomplete deployment configuration (never includes secret values)."""


def validate_production(settings: Settings) -> None:
    """Fail closed when an Internet-facing API is configured as production."""
    if settings.environment != "production":
        return
    token = settings.api_token.get_secret_value() if settings.api_token else ""
    if settings.auth_mode != "token" or len(token.strip()) < 32:
        raise DeploymentError(
            "Production requires token auth and an EZO_API_TOKEN of 32+ characters."
        )
    if settings.expose_debug_traces or settings.log_level.upper() not in {
        "INFO",
        "WARNING",
        "ERROR",
    }:
        raise DeploymentError(
            "Production requires EZO_DEBUG_TRACES=false and INFO/WARNING/ERROR logs."
        )
    if settings.fetch_allow_private_networks:
        raise DeploymentError("Production requires EZO_FETCH_ALLOW_PRIVATE_NETWORKS=false.")
    if not settings.cors_origins:
        raise DeploymentError("Production requires an explicit EZO_CORS_ORIGINS allowlist.")
    for origin in settings.cors_origins:
        try:
            parsed = urlsplit(origin)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and "*" not in origin
                and parsed.port != 0
            )
        except ValueError:
            valid = False
        if not valid:
            raise DeploymentError(
                "Production CORS entries must be exact HTTPS origins without paths."
            )
    try:
        database = urlsplit(settings.database_url)
        query = parse_qs(database.query)
        valid_database = (
            database.scheme in {"postgres", "postgresql", "postgresql+psycopg"}
            and database.hostname
            and query.get("sslmode") == ["verify-full"]
        )
    except ValueError:
        valid_database = False
    if not valid_database:
        raise DeploymentError(
            "Production requires a PostgreSQL DATABASE_URL with sslmode=verify-full."
        )
    if not settings.storage_dir.is_absolute():
        raise DeploymentError("Production EZO_STORAGE_DIR must be an absolute durable-volume path.")


class ProductionFormatter(logging.Formatter):
    """Redact configured credentials and suppress exception payloads in production."""

    def __init__(self, settings: Settings) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        values = [
            value.get_secret_value()
            for name in type(settings).model_fields
            if isinstance(value := getattr(settings, name), SecretStr)
        ]
        # Database URLs are not SecretStr in the shared settings model.
        values.append(settings.database_url)
        password = urlsplit(settings.database_url).password
        if password:
            values.extend([password, unquote(password)])
        self._secrets = sorted({value for value in values if value}, key=len, reverse=True)

    def formatException(
        self,
        ei: tuple[type[BaseException], BaseException, TracebackType | None]
        | tuple[None, None, None],
    ) -> str:
        # SDK/SQL exception payloads can contain credentials, prompts or document text.
        name = ei[0].__name__ if ei[0] else "unknown"
        return f"exception={name} (details withheld in production)"

    def format(self, record: logging.LogRecord) -> str:
        safe_record = logging.makeLogRecord(record.__dict__.copy())
        safe_record.exc_text = None
        result = super().format(safe_record)
        for value in self._secrets:
            result = result.replace(value, "[REDACTED]")
        return result


def configure_production_logging(settings: Settings) -> None:
    if settings.environment != "production":
        return
    formatter = ProductionFormatter(settings)
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)
    for name in ("httpx", "httpcore", "openai", "anthropic", "google_genai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    """Preflight before Alembic: bad configuration must not mutate the database."""
    settings = Settings()
    validate_production(settings)
    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=settings.storage_dir):
            pass
    except OSError:
        raise DeploymentError("EZO_STORAGE_DIR must be writable by the API user.") from None


if __name__ == "__main__":
    main()
