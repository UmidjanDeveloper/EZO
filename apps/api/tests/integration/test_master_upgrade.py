"""0019->0021 preserves actual Student data and closes hostile Data API defaults."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from ezo_api.db.session import to_sync_url
from ezo_api.settings import API_DIR
from tests.integration.test_student_study import card


def migrate(url, revision, *, down=False):
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    (command.downgrade if down else command.upgrade)(config, revision)


async def test_existing_student_data_survives_additive_master_migrations(client, app, database_url):
    created, _user = await card(client, app)
    migrate(database_url, "0019", down=True)
    engine = create_engine(to_sync_url(database_url))
    postgres = engine.dialect.name == "postgresql"
    try:
        if postgres:
            with engine.begin() as connection:
                connection.execute(
                    text("""DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        CREATE ROLE anon NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        CREATE ROLE authenticated NOLOGIN;
                    END IF;
                END $$""")
                )
                connection.execute(
                    text(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                        "GRANT ALL ON TABLES TO PUBLIC, anon, authenticated"
                    )
                )
        migrate(database_url, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0022"
            if postgres:
                names = [
                    "source_refresh_policies",
                    "source_refresh_runs",
                    "source_refresh_blobs",
                    "student_learning_paths",
                ]
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM information_schema.table_privileges "
                            "WHERE table_schema='public' AND table_name=ANY(:names) "
                            "AND grantee IN ('PUBLIC','anon','authenticated')"
                        ),
                        {"names": names},
                    )
                    == 0
                )
        cards = (await client.get("/api/student/cards")).json()
        assert len(cards) == 1 and cards[0]["id"] == created["id"]
        assert cards[0]["quote"] == created["quote"]
        assert cards[0]["revision_id"] == created["revision_id"]
        result = await client.post(
            f"/api/student/cards/{created['id']}/review",
            json={
                "event_id": "aef01699-68c9-4d13-85f5-f2c43964d558",
                "expected_version": 0,
                "rating": "good",
            },
        )
        assert result.status_code == 200, result.text
    finally:
        if postgres:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                        "REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated"
                    )
                )
        engine.dispose()
