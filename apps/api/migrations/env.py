"""Alembic environment: runs migrations with a synchronous driver."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from ezo_api.db import models  # noqa: F401  (registers tables)
from ezo_api.db.base import Base
from ezo_api.db.session import to_sync_url
from ezo_api.deployment import configure_production_logging
from ezo_api.settings import get_settings

config = context.config
if config.config_file_name is not None and not os.environ.get("EZO_ALEMBIC_SKIP_LOGGING"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
    # Production: the same redaction as the API (SQL errors can carry parameters).
    configure_production_logging(get_settings())

target_metadata = Base.metadata
LOCK_KEY = 7_352_901  # arbitrary, constant: "EZO migrations"

# Tables managed with raw SQL (only on PostgreSQL with pgvector); not in the ORM.
RAW_SQL_TABLES = {"pgvector_entries"}
RAW_SQL_INDEXES = {"ix_knowledge_chunks_fts"}


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    if type_ == "table" and name in RAW_SQL_TABLES:
        return False
    if type_ == "index" and name in RAW_SQL_INDEXES:
        return False
    table = getattr(obj, "table", None)
    return not (type_ in ("index", "column") and getattr(table, "name", None) in RAW_SQL_TABLES)


def _database_url() -> str:
    override = config.attributes.get("database_url")
    url = override if isinstance(override, str) else get_settings().database_url
    return to_sync_url(url)


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=url.startswith("sqlite"),
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
            include_object=include_object,
        )
        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                # One migrator at a time (several instances starting together wait here).
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
