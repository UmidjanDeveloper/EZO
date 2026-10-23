"""Durable permission-fenced source refresh and pre-write cleanup journal.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "source_refresh_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("learned_sources.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("generation >= 1", name="generation"),
        sa.CheckConstraint("interval_seconds IS NULL OR interval_seconds >= 3600", name="interval"),
    )
    op.create_index("ix_source_refresh_due", "source_refresh_policies", ["enabled", "next_run_at"])
    op.create_table(
        "source_refresh_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("learned_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("active_key", sa.String(36), nullable=True, unique=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("input", json_type, nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("result", json_type, nullable=True),
        sa.UniqueConstraint("source_id", "request_id"),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="attempts"),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')", name="state"
        ),
    )
    op.create_index(
        "ix_source_refresh_queue", "source_refresh_runs", ["state", "available_at", "created_at"]
    )
    op.create_table(
        "source_refresh_blobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("source_refresh_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("next_cleanup_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_source_refresh_blob_cleanup", "source_refresh_blobs", ["published", "next_cleanup_at"]
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
            op.execute(
                "REVOKE ALL ON source_refresh_policies, source_refresh_runs, "
                "source_refresh_blobs FROM " + suffix
            )


def downgrade() -> None:
    op.drop_table("source_refresh_blobs")
    op.drop_table("source_refresh_runs")
    op.drop_table("source_refresh_policies")
