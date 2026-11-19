# ruff: noqa: E501
"""Jadval: recurring jobs and their runs

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ezo_api.db.base

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("weekdays", sa.String(length=20), nullable=False),
        sa.Column("month_day", sa.Integer(), nullable=True),
        sa.Column("at_time", sa.String(length=5), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("notify_recipient_id", sa.Uuid(), nullable=True),
        sa.Column("next_run_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("locked_until", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('weekly_report','monthly_report','deadline_digest','district_sync','lexuz_recheck')",
            name=op.f("ck_scheduled_jobs_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["notify_recipient_id"],
            ["telegram_recipients.id"],
            name=op.f("fk_scheduled_jobs_notify_recipient_id_telegram_recipients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_scheduled_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_jobs")),
    )
    with op.batch_alter_table("scheduled_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_scheduled_jobs_due", ["enabled", "next_run_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_scheduled_jobs_user_id"), ["user_id"], unique=False)

    op.create_table(
        "scheduled_runs",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("finished_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')", name=op.f("ck_scheduled_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_scheduled_runs_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["scheduled_jobs.id"],
            name=op.f("fk_scheduled_runs_job_id_scheduled_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_scheduled_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_runs")),
    )
    with op.batch_alter_table("scheduled_runs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_scheduled_runs_job_started", ["job_id", "started_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_scheduled_runs_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("scheduled_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scheduled_runs_user_id"))
        batch_op.drop_index("ix_scheduled_runs_job_started")

    op.drop_table("scheduled_runs")
    with op.batch_alter_table("scheduled_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scheduled_jobs_user_id"))
        batch_op.drop_index("ix_scheduled_jobs_due")

    op.drop_table("scheduled_jobs")
