"""District center: projects, members, assignments, progress, notices

Revision ID: 0025
Revises: 0024

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import ezo_api.db.base

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "district_projects",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "aliases",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("responsible_org", sa.String(length=160), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "source",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_sync_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('manual','import','api')",
            name=op.f("ck_district_projects_source_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','finished')", name=op.f("ck_district_projects_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_district_projects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district_projects")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_district_projects_user_id")),
    )
    with op.batch_alter_table("district_projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_district_projects_user_id"), ["user_id"], unique=False)

    op.create_table(
        "district_members",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("position", sa.String(length=160), nullable=False),
        sa.Column("area", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("external_id", sa.String(length=80), nullable=True),
        sa.Column("telegram_recipient_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_recipient_id"],
            ["telegram_recipients.id"],
            name=op.f("fk_district_members_telegram_recipient_id_telegram_recipients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_district_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district_members")),
    )
    with op.batch_alter_table("district_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_district_members_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "ix_district_members_user_name", ["user_id", "full_name"], unique=False
        )

    op.create_table(
        "district_assignments",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("done", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("reported_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["district_members.id"],
            name=op.f("fk_district_assignments_member_id_district_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["district_projects.id"],
            name=op.f("fk_district_assignments_project_id_district_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district_assignments")),
        sa.UniqueConstraint(
            "project_id", "member_id", name=op.f("uq_district_assignments_project_id")
        ),
    )
    with op.batch_alter_table("district_assignments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_district_assignments_member_id"), ["member_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_district_assignments_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "district_notices",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_name", sa.String(length=160), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "channels",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sender", sa.String(length=160), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column(
            "results",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','sent','partly_sent','failed','cancelled')",
            name=op.f("ck_district_notices_status"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_district_notices_approved_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["district_members.id"],
            name=op.f("fk_district_notices_member_id_district_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["district_projects.id"],
            name=op.f("fk_district_notices_project_id_district_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_district_notices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district_notices")),
    )
    with op.batch_alter_table("district_notices", schema=None) as batch_op:
        batch_op.create_index(
            "ix_district_notices_user_created", ["user_id", "created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_district_notices_user_id"), ["user_id"], unique=False)

    op.create_table(
        "district_progress",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("done", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("recorded_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["district_assignments.id"],
            name=op.f("fk_district_progress_assignment_id_district_assignments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district_progress")),
    )
    with op.batch_alter_table("district_progress", schema=None) as batch_op:
        batch_op.create_index(
            "ix_district_progress_assignment_time", ["assignment_id", "recorded_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("district_progress", schema=None) as batch_op:
        batch_op.drop_index("ix_district_progress_assignment_time")

    op.drop_table("district_progress")
    with op.batch_alter_table("district_notices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_district_notices_user_id"))
        batch_op.drop_index("ix_district_notices_user_created")

    op.drop_table("district_notices")
    with op.batch_alter_table("district_assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_district_assignments_project_id"))
        batch_op.drop_index(batch_op.f("ix_district_assignments_member_id"))

    op.drop_table("district_assignments")
    with op.batch_alter_table("district_members", schema=None) as batch_op:
        batch_op.drop_index("ix_district_members_user_name")
        batch_op.drop_index(batch_op.f("ix_district_members_user_id"))

    op.drop_table("district_members")
    with op.batch_alter_table("district_projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_district_projects_user_id"))

    op.drop_table("district_projects")
