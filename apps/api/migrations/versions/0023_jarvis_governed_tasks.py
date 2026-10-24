"""JARVIS durable governed tasks: paired devices, tasks/steps, approvals, recipients.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import ezo_api.db.base

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jarvis_devices",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("public_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=True),
        sa.Column("code_expires_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("confirm_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "capabilities",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("paired_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "platform IN ('windows','android','linux','chrome')",
            name=op.f("ck_jarvis_devices_platform"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','paired','revoked')", name=op.f("ck_jarvis_devices_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_jarvis_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jarvis_devices")),
        sa.UniqueConstraint("public_key", name=op.f("uq_jarvis_devices_public_key")),
    )
    op.create_index("ix_jarvis_devices_user", "jarvis_devices", ["user_id", "status"], unique=False)
    op.create_table(
        "telegram_recipients",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("link_code_sha256", sa.String(length=64), nullable=True),
        sa.Column("link_expires_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("chat_id", sa.String(length=32), nullable=True),
        sa.Column("telegram_name", sa.String(length=120), nullable=True),
        sa.Column("verified_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','verified','revoked')", name=op.f("ck_telegram_recipients_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_telegram_recipients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_recipients")),
        sa.UniqueConstraint("user_id", "label", name=op.f("uq_telegram_recipients_user_id")),
    )
    op.create_table(
        "jarvis_tasks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column(
            "plan",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("finished_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued','awaiting_authorization','running','completed','failed',"
            "'cancelled')",
            name=op.f("ck_jarvis_tasks_state"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["jarvis_devices.id"],
            name=op.f("fk_jarvis_tasks_device_id_jarvis_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_jarvis_tasks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jarvis_tasks")),
        sa.UniqueConstraint("user_id", "idempotency_key", name=op.f("uq_jarvis_tasks_user_id")),
    )
    op.create_index("ix_jarvis_tasks_runnable", "jarvis_tasks", ["state"], unique=False)
    op.create_index("ix_jarvis_tasks_user", "jarvis_tasks", ["user_id", "created_at"], unique=False)
    op.create_table(
        "jarvis_task_steps",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column(
            "params",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "receipt",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("scope_sha256", sa.String(length=64), nullable=True),
        sa.Column("device_request_id", sa.Uuid(), nullable=True),
        sa.Column(
            "device_request_expires_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True
        ),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.String(length=300), nullable=True),
        sa.Column("started_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("finished_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending','awaiting_authorization','awaiting_device','running',"
            "'completed','failed','cancelled')",
            name=op.f("ck_jarvis_task_steps_state"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["jarvis_tasks.id"],
            name=op.f("fk_jarvis_task_steps_task_id_jarvis_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jarvis_task_steps")),
        sa.UniqueConstraint("task_id", "position", name=op.f("uq_jarvis_task_steps_task_id")),
    )
    op.create_table(
        "jarvis_authorizations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("scope_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("used_at", ezo_api.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')", name=op.f("ck_jarvis_authorizations_decision")
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["jarvis_task_steps.id"],
            name=op.f("fk_jarvis_authorizations_step_id_jarvis_task_steps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["jarvis_tasks.id"],
            name=op.f("fk_jarvis_authorizations_task_id_jarvis_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_jarvis_authorizations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jarvis_authorizations")),
        sa.UniqueConstraint("step_id", name=op.f("uq_jarvis_authorizations_step_id")),
    )

    if op.get_bind().dialect.name == "postgresql":
        # Same hardening as 0019-0021: no Supabase Data API role sees these tables.
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
            op.execute(
                "REVOKE ALL ON jarvis_devices, telegram_recipients, jarvis_tasks, "
                "jarvis_task_steps, jarvis_authorizations FROM " + suffix
            )


def downgrade() -> None:
    op.drop_table("jarvis_authorizations")
    op.drop_table("jarvis_task_steps")
    op.drop_index("ix_jarvis_tasks_user", table_name="jarvis_tasks")
    op.drop_index("ix_jarvis_tasks_runnable", table_name="jarvis_tasks")
    op.drop_table("jarvis_tasks")
    op.drop_table("telegram_recipients")
    op.drop_index("ix_jarvis_devices_user", table_name="jarvis_devices")
    op.drop_table("jarvis_devices")
