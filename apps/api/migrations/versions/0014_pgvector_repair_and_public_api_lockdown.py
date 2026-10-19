"""pgvector repair and public data API lockdown (PostgreSQL only)

1. Migration 0002 creates `pgvector_entries` only when the `vector` extension is already
   installed or the role is a superuser. On hosted PostgreSQL (e.g. Supabase) the role is
   not a superuser, so when the extension was enabled after 0002 the table never
   existed and EZO silently used the slower local vector store. This migration enables
   the extension when the host allows it and creates the table when it is missing.
2. Supabase exposes the `public` schema through its Data API to the `anon` and
   `authenticated` roles. EZO never uses that API, so every privilege of those roles on
   EZO's tables, sequences and functions is revoked, also for objects created later.
   Nothing happens where the roles do not exist.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLIC_API_ROLES = ("anon", "authenticated")


def _scalar(bind: sa.engine.Connection, sql: str, **params: object) -> object:
    return bind.execute(sa.text(sql), params).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if not _scalar(bind, "SELECT 1 FROM pg_extension WHERE extname = 'vector'") and _scalar(
        bind, "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
    ):
        nested = bind.begin_nested()
        try:
            bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            nested.commit()
        except sa.exc.DBAPIError:
            nested.rollback()  # not allowed for this role: the owner enables it (runbook)
    has_vector = _scalar(bind, "SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    if has_vector and not _scalar(bind, "SELECT to_regclass('public.pgvector_entries')"):
        op.execute(
            """
            CREATE TABLE pgvector_entries (
                id uuid PRIMARY KEY,
                user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                owner_type varchar(20) NOT NULL,
                owner_id uuid NOT NULL,
                document_id uuid,
                project_id uuid,
                model varchar(120) NOT NULL,
                dim integer NOT NULL,
                embedding vector NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (owner_type, owner_id, model)
            )
            """
        )
        op.execute(
            "CREATE INDEX ix_pgvector_entries_scope "
            "ON pgvector_entries (user_id, owner_type, model)"
        )

    for role in PUBLIC_API_ROLES:
        if not _scalar(bind, "SELECT 1 FROM pg_roles WHERE rolname = :r", r=role):
            continue
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            op.execute(f"REVOKE ALL ON ALL {kind} IN SCHEMA public FROM {role}")
            op.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON {kind} FROM {role}"
            )


def downgrade() -> None:
    # Deliberately nothing: re-granting the public Data API roles or dropping stored
    # vectors would be unsafe. 0002's downgrade still drops pgvector_entries.
    pass
