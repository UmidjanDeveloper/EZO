"""Owner-managed accounts: user tier/status, hashed per-user API tokens, usage events.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ezo_api.db.base

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("expires_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_tokens")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_user_tokens_token_sha256")),
    )
    op.create_index("ix_user_tokens_user", "user_tokens", ["user_id"], unique=False)
    op.create_table(
        "usage_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("quota", sa.String(length=40), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_usage_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
    )
    op.create_index(
        "ix_usage_events_user_quota_time",
        "usage_events",
        ["user_id", "quota", "created_at"],
        unique=False,
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tier", sa.String(length=16), server_default="free", nullable=False)
        )
        batch_op.add_column(
            sa.Column("status", sa.String(length=16), server_default="active", nullable=False)
        )
        batch_op.create_check_constraint("tier", "tier IN ('free','pro','premium')")
        batch_op.create_check_constraint("status", "status IN ('active','disabled')")
    if op.get_bind().dialect.name == "postgresql":
        # Same hardening as 0019-0023: no Supabase Data API role sees token hashes or usage.
        roles = (
            op.get_bind()
            .execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
            )
            .scalars()
            .all()
        )
        for table in ("user_tokens", "usage_events"):
            for role in ["PUBLIC", *roles]:
                suffix = '"' + role + '"' if role != "PUBLIC" else "PUBLIC"
                op.execute("REVOKE ALL ON " + table + " FROM " + suffix)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("status", type_="check")
        batch_op.drop_constraint("tier", type_="check")
        batch_op.drop_column("status")
        batch_op.drop_column("tier")
    op.drop_index("ix_usage_events_user_quota_time", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_user_tokens_user", table_name="user_tokens")
    op.drop_table("user_tokens")
