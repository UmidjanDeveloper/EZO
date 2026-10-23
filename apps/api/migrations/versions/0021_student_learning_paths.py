"""Owner-defined source-bound adaptive recall paths.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_learning_paths",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("goal_id", sa.Uuid(), sa.ForeignKey("personal_goals.id", ondelete="SET NULL")),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column(
            "steps", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.CheckConstraint("version >= 0 AND version <= 10000", name="version"),
        sa.CheckConstraint("state IN ('active','paused','deleted')", name="state"),
    )
    op.create_index(
        "ix_student_learning_paths_scope",
        "student_learning_paths",
        ["user_id", "project_id", "state"],
    )
    if op.get_bind().dialect.name == "postgresql":
        roles = (
            op.get_bind()
            .execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
            )
            .scalars()
            .all()
        )
        for role in ["PUBLIC", *roles]:
            suffix = '"' + role + '"' if role != "PUBLIC" else "PUBLIC"
            op.execute("REVOKE ALL ON student_learning_paths FROM " + suffix)


def downgrade() -> None:
    op.drop_table("student_learning_paths")
