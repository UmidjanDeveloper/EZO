"""Invites and passwords for owner-invited accounts

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ezo_api.db.base

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_invites",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("used_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_user_invites_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_invites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_invites")),
        sa.UniqueConstraint("code_sha256", name=op.f("uq_user_invites_code_sha256")),
    )
    with op.batch_alter_table("user_invites", schema=None) as batch_op:
        batch_op.create_index("ix_user_invites_user", ["user_id"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_hash")

    with op.batch_alter_table("user_invites", schema=None) as batch_op:
        batch_op.drop_index("ix_user_invites_user")

    op.drop_table("user_invites")
