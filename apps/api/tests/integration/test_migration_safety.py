"""PostgreSQL migration 0014 on a Supabase-like database: the public Data API roles lose
every privilege, a missing pgvector table is repaired, and the post-migration preflight
refuses to start while either problem exists."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from ezo_api.db.session import to_sync_url
from ezo_api.deployment import DeploymentError, check_database
from ezo_api.settings import API_DIR, Settings

URL = os.environ.get("EZO_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL.startswith("postgres"), reason="needs PostgreSQL (EZO_TEST_DATABASE_URL)"
)


def alembic(url: str, action: str, target: str) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    os.environ["EZO_ALEMBIC_SKIP_LOGGING"] = "1"
    getattr(command, action)(config, target)


def settings(url: str) -> Settings:
    return Settings(
        _env_file=None,
        EZO_ENV="production",
        DATABASE_URL=url,
        EZO_VECTOR_STORE="pgvector",
    )  # type: ignore[call-arg]


def test_public_api_roles_are_locked_out_and_pgvector_is_repaired(database_url: str) -> None:
    engine = create_engine(to_sync_url(database_url))
    with engine.begin() as connection:
        if not connection.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ):
            pytest.skip("creating the Supabase-like roles needs a superuser")
        for role in ("anon", "authenticated"):  # constant names, not user input
            create = f"CREATE ROLE {role} NOLOGIN"
            exists = connection.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
            )
            if not exists:
                connection.execute(text(create))
    alembic(database_url, "downgrade", "0013")
    with engine.begin() as connection:
        # What Supabase does by default, and what an extension enabled too late leaves.
        connection.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated"))
        connection.execute(text("DROP TABLE IF EXISTS pgvector_entries"))
    with pytest.raises(DeploymentError):
        check_database(settings(database_url))

    alembic(database_url, "upgrade", "head")
    with engine.connect() as connection:
        grants = connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.role_table_grants WHERE "
                "table_schema = 'public' AND grantee IN ('anon', 'authenticated')"
            )
        )
        assert grants == 0
        assert connection.scalar(text("SELECT to_regclass('public.pgvector_entries')"))
    check_database(settings(database_url))  # passes now

    # Tables created later stay closed too (default privileges were revoked).
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE later_table (id int)"))
        assert not connection.scalar(
            text("SELECT has_table_privilege('anon', 'later_table', 'SELECT')")
        )
        connection.execute(text("DROP TABLE later_table"))
        connection.execute(text("GRANT SELECT ON users TO anon"))
    with pytest.raises(DeploymentError, match="anon/authenticated"):
        check_database(settings(database_url))
    engine.dispose()
