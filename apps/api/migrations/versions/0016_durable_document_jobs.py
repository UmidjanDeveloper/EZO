"""durable_document_jobs

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-20 09:53:08.969126
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_jobs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("input_revision_id", sa.Uuid(), nullable=False),
        sa.Column("input_content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(state = 'running' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (state != 'running' AND lease_expires_at IS NULL)",
            name=op.f("ck_document_jobs_lease"),
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')",
            name=op.f("ck_document_jobs_state"),
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts", name=op.f("ck_document_jobs_attempts")
        ),
        sa.CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 5", name=op.f("ck_document_jobs_retry_bound")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_document_jobs_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_revision_id"],
            ["document_revisions.id"],
            name=op.f("fk_document_jobs_input_revision_id_document_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_document_jobs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_jobs")),
        sa.UniqueConstraint(
            "document_id",
            "input_revision_id",
            "parser_version",
            name=op.f("uq_document_jobs_document_id"),
        ),
    )
    with op.batch_alter_table("document_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_document_jobs_claim", ["state", "available_at"], unique=False)
        batch_op.create_index(
            "ix_document_jobs_scope", ["user_id", "project_id", "id"], unique=False
        )

    op.create_index("ix_document_jobs_lease", "document_jobs", ["state", "lease_expires_at"])

    op.create_table(
        "document_job_publications",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("input_revision_id", sa.Uuid(), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "spans",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["input_revision_id"],
            ["document_revisions.id"],
            name=op.f("fk_document_job_publications_input_revision_id_document_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["document_jobs.id"],
            name=op.f("fk_document_job_publications_job_id_document_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_job_publications")),
        sa.UniqueConstraint("job_id", name=op.f("uq_document_job_publications_job_id")),
    )

    if op.get_bind().dialect.name == "postgresql":
        roles = (
            op.get_bind()
            .execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
            )
            .scalars()
            .all()
        )
        for table in ("document_jobs", "document_job_publications"):
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            for role in roles:
                op.execute(f'REVOKE ALL ON TABLE public.{table} FROM "{role}"')


def downgrade() -> None:
    op.drop_table("document_job_publications")
    with op.batch_alter_table("document_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_document_jobs_lease")
        batch_op.drop_index("ix_document_jobs_scope")
        batch_op.drop_index("ix_document_jobs_claim")

    op.drop_table("document_jobs")
