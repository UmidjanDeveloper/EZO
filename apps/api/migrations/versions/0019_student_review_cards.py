"""Source-bound study cards and idempotent review history.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_cards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("document_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("front", sa.String(600), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 0 AND interval_days >= 0", name="schedule"),
        sa.CheckConstraint("quote_start >= 0 AND quote_end > quote_start", name="quote"),
    )
    op.create_index("ix_study_cards_user_due", "study_cards", ["user_id", "due_at"])
    op.create_table(
        "study_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(),
            sa.ForeignKey("study_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column(
            "result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("card_id", "event_id"),
    )
    op.create_index("ix_study_reviews_card_id", "study_reviews", ["card_id"])
    if op.get_bind().dialect.name == "postgresql":
        # Supabase may grant newly created public tables to API roles by default.
        roles = (
            op.get_bind()
            .execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
            )
            .scalars()
            .all()
        )
        for role in ["PUBLIC", *roles]:
            op.execute(
                f'REVOKE ALL ON study_cards, study_reviews FROM "{role}"'
                if role != "PUBLIC"
                else "REVOKE ALL ON study_cards, study_reviews FROM PUBLIC"
            )


def downgrade() -> None:
    op.drop_table("study_reviews")
    op.drop_table("study_cards")
