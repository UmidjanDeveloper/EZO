"""Regression checks for the Internet-facing single-owner deployment boundary."""

from __future__ import annotations

import logging

import pytest

from ezo_api.deployment import DeploymentError, ProductionFormatter, validate_production
from ezo_api.settings import Settings


def production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "EZO_ENV": "production",
        "EZO_AUTH_MODE": "token",
        "EZO_API_TOKEN": "private-beta-owner-test-token-32-characters",
        "EZO_DEBUG_TRACES": "false",
        "EZO_CORS_ORIGINS": "https://ezo.example.com",
        "DATABASE_URL": "postgresql://owner:db-test-password@db.example.com/ezo?sslmode=verify-full",
        "EZO_STORAGE_DIR": "/app/storage",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_accepts_a_session_connection_and_explicit_owner() -> None:
    validate_production(production())


@pytest.mark.parametrize(
    "overrides",
    [
        {"EZO_AUTH_MODE": "local"},
        {"EZO_API_TOKEN": ""},
        {"EZO_API_TOKEN": "short"},
        {"EZO_DEBUG_TRACES": "true"},
        {"EZO_LOG_LEVEL": "DEBUG"},
        {"EZO_FETCH_ALLOW_PRIVATE_NETWORKS": "true"},
        {"EZO_CORS_ORIGINS": "*"},
        {"EZO_CORS_ORIGINS": ""},
        {"EZO_CORS_ORIGINS": "https://*.example.com"},
        {"EZO_CORS_ORIGINS": "http://ezo.example.com"},
        {"EZO_CORS_ORIGINS": "https://ezo.example.com/path"},
        {"EZO_CORS_ORIGINS": "https://user:password@ezo.example.com"},
        {"EZO_CORS_ORIGINS": "https://ezo.example.com:invalid"},
        {"DATABASE_URL": "sqlite:///ezo.db"},
        {"DATABASE_URL": "postgresql://owner@db.example.com/ezo?sslmode=require"},
        {"DATABASE_URL": "postgresql://owner@db.example.com/ezo?sslmode=disable"},
        {"EZO_STORAGE_DIR": "relative-storage"},
    ],
)
def test_production_rejects_unsafe_defaults(overrides: dict[str, object]) -> None:
    with pytest.raises(DeploymentError):
        validate_production(production(**overrides))


def test_local_sqlite_workflow_stays_available() -> None:
    validate_production(Settings(_env_file=None, DATABASE_URL="sqlite:///ezo.db"))


def test_production_logs_redact_credentials_and_exception_payloads() -> None:
    settings = production(ANTHROPIC_API_KEY="provider-test-secret")
    formatter = ProductionFormatter(settings)
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "provider-test-secret db-test-password " + settings.database_url,
        (),
        None,
    )
    try:
        raise RuntimeError("sensitive document content and provider-test-secret")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    output = formatter.format(record)
    assert "provider-test-secret" not in output
    assert "db-test-password" not in output
    assert "sensitive document content" not in output
    assert "exception=RuntimeError" in output


def test_a_hosting_platform_requires_production_mode() -> None:
    from ezo_api.deployment import check_environment

    development = Settings(_env_file=None, DATABASE_URL="sqlite:///ezo.db")
    check_environment(development, {})  # own computer: fine
    for marker in ("RENDER", "K_SERVICE", "FLY_APP_NAME", "RAILWAY_ENVIRONMENT", "DYNO"):
        with pytest.raises(DeploymentError, match="EZO_ENV=production"):
            check_environment(development, {marker: "true"})
    check_environment(production(), {"RENDER": "true"})


def test_transaction_pooler_is_refused() -> None:
    url = "postgresql://owner:pw@pooler.example.com:6543/ezo?sslmode=verify-full"
    with pytest.raises(DeploymentError, match="session connection"):
        validate_production(production(DATABASE_URL=url))


def test_production_storage_must_be_a_mounted_disk(tmp_path: object) -> None:
    from pathlib import Path

    from ezo_api.deployment import VOLUME_SENTINEL, check_storage

    folder = Path(str(tmp_path)) / "storage"
    check_storage(Settings(_env_file=None, EZO_STORAGE_DIR=str(folder)))  # development: fine
    with pytest.raises(DeploymentError, match="not a mounted disk"):
        check_storage(production(EZO_STORAGE_DIR=str(folder)))
    (folder / VOLUME_SENTINEL).write_text("provisioned")
    check_storage(production(EZO_STORAGE_DIR=str(folder)))
