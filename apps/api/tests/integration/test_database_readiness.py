"""A Data API role inherits PUBLIC access even without a direct grant."""

import pytest
from sqlalchemy import create_engine, text

from ezo_api.deployment import DeploymentError, check_database
from ezo_api.settings import Settings


@pytest.mark.parametrize("grant", ["SELECT", "SELECT(email)"])
def test_readiness_detects_inherited_public_privileges(database_url: str, grant: str) -> None:
    if not database_url.startswith("postgresql"):
        pytest.skip("requires PostgreSQL role privilege checks")
    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon NOLOGIN;
                  END IF;
                END $$;
            """)
            )
            connection.execute(text(f"GRANT {grant} ON public.users TO PUBLIC"))
        settings = Settings(
            _env_file=None,
            EZO_ENV="production",
            DATABASE_URL=database_url,
            EZO_VECTOR_STORE="pgvector",
        )
        try:
            with pytest.raises(DeploymentError, match="public Data API"):
                check_database(settings)
        finally:
            with engine.begin() as connection:
                connection.execute(text("REVOKE SELECT ON public.users FROM PUBLIC"))
                connection.execute(text("REVOKE SELECT(email) ON public.users FROM PUBLIC"))
        check_database(settings)
    finally:
        engine.dispose()


def test_full_profile_refuses_privileged_role_before_migration(database_url: str) -> None:
    if not database_url.startswith("postgres"):
        pytest.skip("Real PostgreSQL role inheritance catalog")
    from ezo_api.deployment import check_database_role

    settings = Settings(
        _env_file=None,
        EZO_ENV="production",
        DATABASE_URL=database_url,
        EZO_DEPLOYMENT_PROFILE="full",
    )
    with pytest.raises(DeploymentError, match="non-privileged"):
        check_database_role(settings)
