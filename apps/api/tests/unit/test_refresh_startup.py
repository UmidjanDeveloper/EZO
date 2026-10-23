"""A standalone worker never skips application-role or migration startup policy."""

import pytest
from alembic import command
from alembic.config import Config

from ezo_api.deployment import DeploymentError
from ezo_api.learning import refresh_cli
from ezo_api.settings import API_DIR
from tests.conftest import make_settings


async def test_worker_rejects_privileged_role_before_building_any_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(refresh_cli, "Settings", lambda: make_settings("sqlite://"))
    monkeypatch.setattr(refresh_cli, "check_environment", lambda *args: calls.append("environment"))
    monkeypatch.setattr(refresh_cli, "validate_production", lambda *args: calls.append("config"))
    monkeypatch.setattr(refresh_cli, "configure_production_logging", lambda *args: None)

    def reject(settings):
        calls.append("role")
        raise DeploymentError("Privileged test role rejected")

    monkeypatch.setattr(refresh_cli, "check_database_role", reject)

    def forbidden(*args):
        raise AssertionError("Providers must not be built after failed role admission")

    monkeypatch.setattr(refresh_cli, "build_services", forbidden)
    with pytest.raises(DeploymentError, match="role"):
        await refresh_cli.serve()
    assert calls == ["environment", "config", "role"]


def test_worker_requires_exact_current_schema(database_url):
    settings = make_settings(database_url)
    refresh_cli.check_refresh_schema(settings)
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    command.downgrade(config, "0020")
    try:
        with pytest.raises(DeploymentError, match="migration head"):
            refresh_cli.check_refresh_schema(settings)
    finally:
        command.upgrade(config, "head")
    refresh_cli.check_refresh_schema(settings)
