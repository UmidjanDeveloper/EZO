"""Skills: owner-approved tools run in a locked container

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import ezo_api.db.base

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_hint", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_sha256", sa.String(length=64), nullable=True),
        sa.Column("approved_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column(
            "checks",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','approved','disabled')", name=op.f("ck_skills_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_skills_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_skills_user_id")),
    )
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_skills_user_id"), ["user_id"], unique=False)

    op.create_table(
        "skill_runs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "input",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("started_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("finished_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')", name=op.f("ck_skill_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_skill_runs_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_skill_runs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_runs")),
    )
    with op.batch_alter_table("skill_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_skill_runs_skill_id"), ["skill_id"], unique=False)
        batch_op.create_index(
            "ix_skill_runs_status_created", ["status", "created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_skill_runs_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("skill_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_skill_runs_user_id"))
        batch_op.drop_index("ix_skill_runs_status_created")
        batch_op.drop_index(batch_op.f("ix_skill_runs_skill_id"))

    op.drop_table("skill_runs")
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_skills_user_id"))

    op.drop_table("skills")
