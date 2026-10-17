"""artifacts and story projects

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "story_projects",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("visual_style", sa.String(length=200), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=10), nullable=False),
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
            name=op.f("fk_story_projects_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_story_projects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_projects")),
    )
    with op.batch_alter_table("story_projects", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_story_projects_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_story_projects_user_id"), ["user_id"], unique=False)

    op.create_table(
        "artifacts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_agent", sa.String(length=50), nullable=True),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "source_references",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_artifacts_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_artifacts_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_artifacts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
    )
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_artifacts_conversation_id"), ["conversation_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_artifacts_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_artifacts_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_artifacts_user_updated", ["user_id", "updated_at"], unique=False)

    op.create_table(
        "story_scenes",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("layout", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("visual_direction", sa.Text(), nullable=False),
        sa.Column("speaker_notes", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("transition", sa.String(length=40), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["story_projects.id"],
            name=op.f("fk_story_scenes_story_id_story_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_scenes")),
        sa.UniqueConstraint("story_id", "position", name=op.f("uq_story_scenes_story_id")),
    )
    with op.batch_alter_table("story_scenes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_story_scenes_story_id"), ["story_id"], unique=False)

    op.create_table(
        "artifact_versions",
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.String(length=60), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "generation_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "source_references",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_artifact_versions_artifact_id_artifacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["artifact_versions.id"],
            name=op.f("fk_artifact_versions_parent_version_id_artifact_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifact_versions")),
        sa.UniqueConstraint(
            "artifact_id", "version_number", name=op.f("uq_artifact_versions_artifact_id")
        ),
    )
    with op.batch_alter_table("artifact_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_artifact_versions_artifact_id"), ["artifact_id"], unique=False
        )

    op.create_table(
        "story_assets",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("asset_type", sa.String(length=30), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_story_assets_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["story_scenes.id"],
            name=op.f("fk_story_assets_scene_id_story_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["story_projects.id"],
            name=op.f("fk_story_assets_story_id_story_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_assets")),
    )
    with op.batch_alter_table("story_assets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_story_assets_scene_id"), ["scene_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_story_assets_story_id"), ["story_id"], unique=False)

    op.create_table(
        "story_narrations",
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("voice", sa.String(length=80), nullable=False),
        sa.Column(
            "timing",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["story_scenes.id"],
            name=op.f("fk_story_narrations_scene_id_story_scenes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_narrations")),
        sa.UniqueConstraint("scene_id", name=op.f("uq_story_narrations_scene_id")),
    )
    op.create_table(
        "story_timeline",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column(
            "animation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["story_scenes.id"],
            name=op.f("fk_story_timeline_scene_id_story_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["story_projects.id"],
            name=op.f("fk_story_timeline_story_id_story_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_timeline")),
        sa.UniqueConstraint("scene_id", name=op.f("uq_story_timeline_scene_id")),
    )
    with op.batch_alter_table("story_timeline", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_story_timeline_story_id"), ["story_id"], unique=False)

    # Added after artifact_versions exists (the two tables reference each other).
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_artifacts_current_version_id_artifact_versions"),
            "artifact_versions",
            ["current_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_artifacts_current_version_id_artifact_versions"), type_="foreignkey"
        )
    with op.batch_alter_table("story_timeline", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_story_timeline_story_id"))

    op.drop_table("story_timeline")
    op.drop_table("story_narrations")
    with op.batch_alter_table("story_assets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_story_assets_story_id"))
        batch_op.drop_index(batch_op.f("ix_story_assets_scene_id"))

    op.drop_table("story_assets")
    with op.batch_alter_table("artifact_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_artifact_versions_artifact_id"))

    op.drop_table("artifact_versions")
    with op.batch_alter_table("story_scenes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_story_scenes_story_id"))

    op.drop_table("story_scenes")
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.drop_index("ix_artifacts_user_updated")
        batch_op.drop_index(batch_op.f("ix_artifacts_user_id"))
        batch_op.drop_index(batch_op.f("ix_artifacts_project_id"))
        batch_op.drop_index(batch_op.f("ix_artifacts_conversation_id"))

    op.drop_table("artifacts")
    with op.batch_alter_table("story_projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_story_projects_user_id"))
        batch_op.drop_index(batch_op.f("ix_story_projects_project_id"))

    op.drop_table("story_projects")
