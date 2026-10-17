"""Shared fixtures.

Integration tests run against SQLite by default. Set EZO_TEST_DATABASE_URL to a
PostgreSQL URL to run them against PostgreSQL (the schema is reset each test).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from ezo_api.db.session import to_sync_url
from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from ezo_api.settings import API_DIR, Settings
from tests.fakes import FakeProvider


def _reset_postgres(url: str) -> None:
    engine = create_engine(to_sync_url(url))
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def migrate(url: str) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    os.environ["EZO_ALEMBIC_SKIP_LOGGING"] = "1"
    command.upgrade(config, "head")


@pytest.fixture
def database_url(tmp_path: Path) -> Iterator[str]:
    url = os.environ.get("EZO_TEST_DATABASE_URL")
    if url:
        _reset_postgres(url)
    else:
        url = f"sqlite:///{tmp_path / 'ezo-test.db'}"
    migrate(url)
    yield url


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "EZO_ENV": "test",
        "EZO_INGESTION_MODE": "inline",
        "EZO_STORAGE_DIR": str(Path(tempfile.mkdtemp(prefix="ezo-storage-"))),
        "TAVILY_API_KEY": "",
        "EZO_WEB_SEARCH_PROVIDER": "auto",
        "DATABASE_URL": database_url,
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "GEMINI_API_KEY": "",
        "EZO_PREFERRED_PROVIDER": "",
        "EZO_AUTH_MODE": "local",
        "EZO_API_TOKEN": "",
        "VOICESTUDIO_URL": "",
        "EZO_VOICE_PROVIDERS": "auto",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def fake_anthropic() -> FakeProvider:
    return FakeProvider(name="anthropic", reply="Salom! Men EZO, sizga qanday yordam bera olaman?")


@pytest.fixture
def fake_openai() -> FakeProvider:
    # Also the embedding provider (first in models.toml [embeddings]).
    return FakeProvider(
        name="openai", reply="Hello from the fallback provider.", supports_embeddings=True
    )


@pytest.fixture
def providers(fake_anthropic: FakeProvider, fake_openai: FakeProvider) -> dict[str, ModelProvider]:
    return {"anthropic": fake_anthropic, "openai": fake_openai}


@pytest.fixture
def app(database_url: str, providers: dict[str, ModelProvider]) -> FastAPI:
    return create_app(make_settings(database_url), providers=providers)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await app.state.services.db.dispose()
