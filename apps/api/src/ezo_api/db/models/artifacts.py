"""Things EZO creates: artifacts with immutable versions, and story projects.

An `Artifact` is a document, presentation, image, video… that the user can come
back to. Its content lives in `ArtifactVersion` rows; a version is never changed
after it is written — every meaningful edit (or a restore) adds a new version.

A `StoryProject` is the shared content model behind presentations and videos:
ordered scenes with text, visual direction, narration and timing, so one
narrative can later become PPTX, PDF, web slides or a narrated video.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType

ARTIFACT_TYPES = (
    "document",
    "spreadsheet",
    "presentation",
    "image",
    "video",
    "audio",
    "code",
    "report",
    "research",
    "other",
)
ARTIFACT_STATUSES = ("draft", "generating", "ready", "failed")


class Artifact(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Deleting a project keeps its artifacts (like conversations): they just lose the link.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    artifact_type: Mapped[str] = mapped_column("type", String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    created_by_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )


class ArtifactVersion(UUIDPrimaryKey, Base):
    """One immutable version of an artifact's content."""

    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version_number"),)

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # A StorageProvider key (content-addressed), never a filesystem path.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # user | agent:<name> | restore
    created_by: Mapped[str] = mapped_column(String(60), default="user", nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The version this one was derived from (edit, restore, regeneration).
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="SET NULL"), nullable=True
    )
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class StoryProject(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "story_projects"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="uz", nullable=False)
    # presentation | video | both
    format: Mapped[str] = mapped_column(String(20), default="presentation", nullable=False)
    visual_style: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="16:9", nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class StoryScene(UUIDPrimaryKey, Base):
    __tablename__ = "story_scenes"
    __table_args__ = (UniqueConstraint("story_id", "position"),)

    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Slide layout or shot type, e.g. "cover", "big_number", "timeline".
    layout: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    visual_direction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    speaker_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)
    transition: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class StoryAsset(UUIDPrimaryKey, Base):
    __tablename__ = "story_assets"

    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("story_scenes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)  # image | chart | audio…
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class StoryNarration(UUIDPrimaryKey, Base):
    __tablename__ = "story_narrations"

    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_scenes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    voice: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    timing: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class StoryTimeline(UUIDPrimaryKey, Base):
    __tablename__ = "story_timeline"

    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_scenes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    animation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
