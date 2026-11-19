"""Devonxona: appeals, meetings, tasks

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ezo_api.db.base

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gov_appeals",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("applicant", sa.String(length=200), nullable=False),
        sa.Column("contact", sa.String(length=300), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("assignee_member_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("answered_on", sa.Date(), nullable=True),
        sa.Column("answer_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('virtual_reception','president_portal','written','oral','phone','other')",
            name=op.f("ck_gov_appeals_channel"),
        ),
        sa.CheckConstraint(
            "status IN ('new','in_progress','answered','closed')",
            name=op.f("ck_gov_appeals_status"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_gov_appeals_answer_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_member_id"],
            ["district_members.id"],
            name=op.f("fk_gov_appeals_assignee_member_id_district_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_gov_appeals_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_appeals")),
        sa.UniqueConstraint("user_id", "number", name=op.f("uq_gov_appeals_user_id")),
    )
    with op.batch_alter_table("gov_appeals", schema=None) as batch_op:
        batch_op.create_index("ix_gov_appeals_user_due", ["user_id", "due_on"], unique=False)
        batch_op.create_index(batch_op.f("ix_gov_appeals_user_id"), ["user_id"], unique=False)

    op.create_table(
        "gov_meetings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("minutes_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["minutes_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_gov_meetings_minutes_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_gov_meetings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_meetings")),
    )
    with op.batch_alter_table("gov_meetings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_gov_meetings_user_id"), ["user_id"], unique=False)

    op.create_table(
        "gov_tasks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("assignee_member_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_name", sa.String(length=160), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("completed_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','done','cancelled')", name=op.f("ck_gov_tasks_status")
        ),
        sa.ForeignKeyConstraint(
            ["assignee_member_id"],
            ["district_members.id"],
            name=op.f("fk_gov_tasks_assignee_member_id_district_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["gov_meetings.id"],
            name=op.f("fk_gov_tasks_meeting_id_gov_meetings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_gov_tasks_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_tasks")),
        sa.UniqueConstraint("user_id", "number", name=op.f("uq_gov_tasks_user_id")),
    )
    with op.batch_alter_table("gov_tasks", schema=None) as batch_op:
        batch_op.create_index("ix_gov_tasks_user_due", ["user_id", "due_on"], unique=False)
        batch_op.create_index(batch_op.f("ix_gov_tasks_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("gov_tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gov_tasks_user_id"))
        batch_op.drop_index("ix_gov_tasks_user_due")

    op.drop_table("gov_tasks")
    with op.batch_alter_table("gov_meetings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gov_meetings_user_id"))

    op.drop_table("gov_meetings")
    with op.batch_alter_table("gov_appeals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gov_appeals_user_id"))
        batch_op.drop_index("ix_gov_appeals_user_due")

    op.drop_table("gov_appeals")
