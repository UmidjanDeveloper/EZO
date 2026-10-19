"""Deny inherited PUBLIC access to private EZO data.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Dedicated EZO database; PUBLIC grants are inherited by Supabase API roles.
    for kind in ("TABLES", "SEQUENCES"):
        op.execute(f"REVOKE ALL ON ALL {kind} IN SCHEMA public FROM PUBLIC")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON {kind} FROM PUBLIC")
    # Table-level REVOKE does not revoke column-specific grants.
    bind = op.get_bind()
    quote = bind.dialect.identifier_preparer.quote
    tables = bind.execute(
        sa.text("""
        SELECT c.relname, array_agg(a.attname ORDER BY a.attnum) AS columns
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','f')
        GROUP BY c.relname
    """)
    ).all()
    roles = (
        bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
        )
        .scalars()
        .all()
    )
    for table in tables:
        columns = ",".join(quote(name) for name in table.columns)
        for role in ["PUBLIC", *roles]:
            target = "PUBLIC" if role == "PUBLIC" else quote(role)
            op.execute(f"REVOKE ALL ({columns}) ON public.{quote(table.relname)} FROM {target}")


def downgrade() -> None:
    # Never re-open private data as a side effect of a code rollback.
    pass
