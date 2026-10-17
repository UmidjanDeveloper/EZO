"""knowledge base and tool calls

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vector_entries",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column(
            "vector",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vector_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vector_entries")),
        sa.UniqueConstraint(
            "owner_type", "owner_id", "model", name=op.f("uq_vector_entries_owner_type")
        ),
    )
    with op.batch_alter_table("vector_entries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_vector_entries_scope", ["user_id", "owner_type", "model"], unique=False
        )

    op.create_table(
        "knowledge_sources",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_knowledge_sources_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_sources_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_sources")),
    )
    with op.batch_alter_table("knowledge_sources", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_sources_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_knowledge_sources_user_id"), ["user_id"], unique=False)

    op.create_table(
        "knowledge_documents",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("current_revision_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_knowledge_documents_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["knowledge_sources.id"],
            name=op.f("fk_knowledge_documents_source_id_knowledge_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_documents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
    )
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_documents_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_knowledge_documents_source_id"), ["source_id"], unique=False
        )
        batch_op.create_index(
            "ix_knowledge_documents_user_hash", ["user_id", "content_hash"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_knowledge_documents_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "document_revisions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_document_revisions_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_revisions")),
        sa.UniqueConstraint(
            "document_id", "revision_number", name=op.f("uq_document_revisions_document_id")
        ),
    )
    with op.batch_alter_table("document_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_document_revisions_document_id"), ["document_id"], unique=False
        )

    op.create_table(
        "tool_calls",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column(
            "arguments",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_tool_calls_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tool_calls_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_calls")),
    )
    with op.batch_alter_table("tool_calls", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tool_calls_agent_run_id"), ["agent_run_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_tool_calls_user_id"), ["user_id"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["document_revisions.id"],
            name=op.f("fk_knowledge_chunks_revision_id_document_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_chunks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
    )
    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_chunks_document_id"), ["document_id"], unique=False
        )
        batch_op.create_index(
            "ix_knowledge_chunks_revision_index", ["revision_id", "chunk_index"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_knowledge_chunks_user_id"), ["user_id"], unique=False)

    # documents <-> revisions reference each other; add this FK after both exist.
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_knowledge_documents_current_revision_id_document_revisions"),
            "document_revisions",
            ["current_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _upgrade_postgresql(bind)


def _upgrade_postgresql(bind: sa.engine.Connection) -> None:
    """Full-text index, and pgvector storage when the extension can be enabled."""
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks "
        "USING gin (to_tsvector('simple', text))"
    )
    installed = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    superuser = bind.execute(
        sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if not installed and not (available and superuser):
        # EZO then uses LocalVectorStore (vectors in `vector_entries`).
        print("pgvector is not available: EZO will use the portable local vector store.")
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE pgvector_entries (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            owner_type varchar(20) NOT NULL,
            owner_id uuid NOT NULL,
            document_id uuid,
            project_id uuid,
            model varchar(120) NOT NULL,
            dim integer NOT NULL,
            embedding vector NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (owner_type, owner_id, model)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pgvector_entries_scope ON pgvector_entries (user_id, owner_type, model)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS pgvector_entries")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts")
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_knowledge_documents_current_revision_id_document_revisions"),
            type_="foreignkey",
        )
    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_chunks_user_id"))
        batch_op.drop_index("ix_knowledge_chunks_revision_index")
        batch_op.drop_index(batch_op.f("ix_knowledge_chunks_document_id"))

    op.drop_table("knowledge_chunks")
    with op.batch_alter_table("tool_calls", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tool_calls_user_id"))
        batch_op.drop_index(batch_op.f("ix_tool_calls_agent_run_id"))

    op.drop_table("tool_calls")
    with op.batch_alter_table("document_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_revisions_document_id"))

    op.drop_table("document_revisions")
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_user_id"))
        batch_op.drop_index("ix_knowledge_documents_user_hash")
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_source_id"))
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_project_id"))

    op.drop_table("knowledge_documents")
    with op.batch_alter_table("knowledge_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_sources_user_id"))
        batch_op.drop_index(batch_op.f("ix_knowledge_sources_project_id"))

    op.drop_table("knowledge_sources")
    with op.batch_alter_table("vector_entries", schema=None) as batch_op:
        batch_op.drop_index("ix_vector_entries_scope")

    op.drop_table("vector_entries")
