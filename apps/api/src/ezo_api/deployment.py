"""Single-owner production startup policy and logging; independent of agent logic."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from types import TracebackType
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import SecretStr

from ezo_api.settings import Settings

# Variables hosting platforms set inside their containers. Where one is present the API is
# on the Internet, so the safe production policy must be on.
HOSTING_MARKERS = ("RENDER", "K_SERVICE", "FLY_APP_NAME", "RAILWAY_ENVIRONMENT", "DYNO")
VOLUME_SENTINEL = ".ezo-volume"
TRANSACTION_POOLER_PORT = 6543


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
    if database.port == TRANSACTION_POOLER_PORT:
        # Transaction pooling breaks prepared statements and session state.
        raise DeploymentError(
            "Use the session connection (port 5432), not the transaction pooler (6543)."
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


def check_environment(settings: Settings, environ: Mapping[str, str]) -> None:
    """On a hosting platform a forgotten EZO_ENV must not leave the API open (local
    owner mode, API docs, debug traces)."""
    hosted = [name for name in HOSTING_MARKERS if environ.get(name)]
    if hosted and settings.environment != "production":
        raise DeploymentError(
            f"Running on a hosting platform ({hosted[0]} is set): set EZO_ENV=production."
        )


def check_storage(settings: Settings) -> None:
    """Uploads must land on a durable disk, not in the container's temporary layer."""
    storage = settings.storage_dir
    try:
        storage.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=storage):
            pass
    except OSError:
        raise DeploymentError("EZO_STORAGE_DIR must be writable by the API user.") from None
    if settings.environment == "production" and not (
        os.path.ismount(storage) or (storage / VOLUME_SENTINEL).is_file()
    ):
        raise DeploymentError(
            f"EZO_STORAGE_DIR ({storage}) is not a mounted disk. Attach the persistent "
            f"disk there, or create {VOLUME_SENTINEL} in it if the volume is mounted above."
        )


def check_database(settings: Settings) -> None:
    """After migrations: the vector table exists and the public data API cannot read
    EZO's tables (Supabase anon / authenticated roles)."""
    if settings.environment != "production":
        return
    from sqlalchemy import create_engine, text

    from ezo_api.db.session import to_sync_url

    engine = create_engine(to_sync_url(settings.database_url))
    try:
        with engine.connect() as connection:
            if settings.vector_store == "pgvector" and not connection.scalar(
                text("SELECT to_regclass('public.pgvector_entries')")
            ):
                raise DeploymentError(
                    "EZO_VECTOR_STORE=pgvector but pgvector_entries is missing: enable the "
                    "'vector' extension (Supabase: Database → Extensions) and redeploy."
                )
            exposed = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_roles r CROSS JOIN pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE r.rolname IN ('anon', 'authenticated') "
                    "AND n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') "
                    "AND (has_table_privilege(r.oid, c.oid, "
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
                    "OR has_any_column_privilege(r.oid, c.oid, "
                    "'SELECT,INSERT,UPDATE,REFERENCES'))"
                )
            )
            if exposed:
                raise DeploymentError(
                    "The public Data API roles (anon/authenticated) still have privileges on "
                    "EZO tables. Run the migrations again or revoke them."
                )
    finally:
        engine.dispose()


def main(argv: Sequence[str] = ()) -> None:
    """Preflight. Before Alembic: bad configuration must not mutate the database. With
    --after-migrations: database checks before HTTP starts."""
    settings = Settings()
    if "--after-migrations" in argv:
        check_database(settings)
        return
    check_environment(settings, os.environ)
    validate_production(settings)
    check_storage(settings)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except DeploymentError as exc:
        # The message never contains secret values; no traceback with settings in it.
        print(f"EZO startup refused: {exc}", file=sys.stderr)
        sys.exit(1)
