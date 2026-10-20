"""No worker credentials, commands or arbitrary error strings in owner API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: uuid.UUID
    project_id: uuid.UUID | None = None


class CitationSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID | None
    input_revision_id: uuid.UUID
    parser_version: str
    state: Literal["queued", "running", "completed", "failed", "cancelled"]
    attempts: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class PublicationOut(BaseModel):
    """A Unicode page; spans intersect its text but retain global, unclipped offsets.

    Offsets at/beyond total_chars return empty text/spans and preserve offset.
    """

    id: uuid.UUID
    input_revision_id: uuid.UUID
    parser_version: str
    text_sha256: str
    offset_unit: Literal["unicode_codepoints"] = "unicode_codepoints"
    text: str = Field(max_length=8000)
    offset: int
    total_chars: int
    spans: list[CitationSpan] = Field(max_length=1000)
