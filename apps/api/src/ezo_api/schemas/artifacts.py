"""Schemas for artifacts. Mirrored in packages/shared/src/types.ts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ArtifactType = Literal[
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
]
TextFormat = Literal["markdown", "text", "csv", "json", "html"]


class ArtifactVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    filename: str
    mime_type: str
    file_size: int
    content_hash: str
    provider: str | None
    model: str | None
    created_by: str
    change_summary: str | None
    parent_version_id: uuid.UUID | None
    generation_metadata: dict[str, Any]
    source_references: list[dict[str, Any]]
    created_at: datetime
    current: bool
    is_text: bool


class ArtifactOut(BaseModel):
    id: uuid.UUID
    title: str
    type: str
    status: str
    project_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    created_by_agent: str | None
    provider: str | None
    model: str | None
    metadata: dict[str, Any]
    source_references: list[dict[str, Any]]
    current_version: ArtifactVersionOut | None
    version_count: int
    created_at: datetime
    updated_at: datetime


class ArtifactDetailOut(ArtifactOut):
    versions: list[ArtifactVersionOut]


class ArtifactCreateIn(BaseModel):
    """Save text as an artifact (e.g. “save this answer as a document”)."""

    title: str = Field(min_length=1, max_length=300)
    type: ArtifactType = "document"
    format: TextFormat = "markdown"
    content: str = Field(min_length=1, max_length=2_000_000)
    project_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None


class ArtifactRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class ArtifactTextVersionIn(BaseModel):
    """A new version of a text artifact (the previous one is kept)."""

    content: str = Field(min_length=1, max_length=2_000_000)
    change_summary: str = Field(default="", max_length=500)


class ArtifactRef(BaseModel):
    """How a conversation message points to an artifact."""

    id: uuid.UUID
    title: str
    type: str
    version: int
