"""Bounded immutable Student raw inputs.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_raw_revisions",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "length(data) > 0 AND length(data) <= 5242880", name="ck_student_raw_revisions_size"
        ),
        sa.CheckConstraint(
            "format IN ('pdf','docx','epub')", name="ck_student_raw_revisions_format"
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["document_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revision_id"),
    )


def downgrade() -> None:
    op.drop_table("student_raw_revisions")
