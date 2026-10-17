"""Schemas for the knowledge API. Mirrored in packages/shared/src/types.ts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str | None
    source_id: uuid.UUID
    source_type: str
    source_name: str
    project_id: uuid.UUID | None
    mime_type: str
    source_url: str | None
    size_bytes: int
    language: str | None
    status: str
    error: str | None
    chunk_count: int
    current_revision: int | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None
    metadata: dict[str, Any]


class RevisionOut(BaseModel):
    id: uuid.UUID
    revision_number: int
    content_hash: str
    chars: int
    created_at: datetime
    current: bool


class ChunkPreviewOut(BaseModel):
    chunk_index: int
    text: str
    metadata: dict[str, Any]


class KnowledgeDocumentDetailOut(KnowledgeDocumentOut):
    revisions: list[RevisionOut]
    chunks_preview: list[ChunkPreviewOut]


class UploadOut(BaseModel):
    document: KnowledgeDocumentOut
    duplicate: bool
    new_revision: bool


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    project_id: uuid.UUID | None = None


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    project_id: uuid.UUID | None = None
    limit: int = Field(default=6, ge=1, le=20)


class SearchOut(BaseModel):
    mode: str
    results: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class KnowledgeSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    project_id: uuid.UUID | None
    source_url: str | None
    documents: int
    last_sync_at: datetime | None
    created_at: datetime


class KnowledgeStatusOut(BaseModel):
    vector_store: str
    embedding_model: str | None
    semantic_search: bool
    web_search: str | None
    max_upload_mb: int
    allowed_extensions: list[str]
    documents: int
    chunks: int
    by_status: dict[str, int]
