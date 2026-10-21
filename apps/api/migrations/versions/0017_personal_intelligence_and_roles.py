"""personal_intelligence_and_roles

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21 11:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=30), nullable=False, server_default="user")
        )

    op.create_table(
        "personal_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="learning"),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_personal_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personal_goals")),
    )
    with op.batch_alter_table("personal_goals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_personal_goals_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_personal_goals_user_status"), ["user_id", "status"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("personal_goals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_personal_goals_user_status"))
        batch_op.drop_index(batch_op.f("ix_personal_goals_user_id"))
    op.drop_table("personal_goals")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("role")
