"""Telegram inbox for bot messages

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ezo_api.db.base

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_inbox",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.String(length=32), nullable=False),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("received_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("processed_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_inbox")),
        sa.UniqueConstraint("update_id", name=op.f("uq_telegram_inbox_update_id")),
    )
    with op.batch_alter_table("telegram_inbox", schema=None) as batch_op:
        batch_op.create_index("ix_telegram_inbox_chat", ["chat_id", "received_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("telegram_inbox", schema=None) as batch_op:
        batch_op.drop_index("ix_telegram_inbox_chat")

    op.drop_table("telegram_inbox")
