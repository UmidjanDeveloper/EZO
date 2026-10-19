"""conversation library id

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19 10:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("library_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_conversations_library_id_knowledge_libraries"),
            "knowledge_libraries",
            ["library_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_conversations_library_id"), ["library_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_conversations_library_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_conversations_library_id_knowledge_libraries"), type_="foreignkey"
        )
        batch_op.drop_column("library_id")
