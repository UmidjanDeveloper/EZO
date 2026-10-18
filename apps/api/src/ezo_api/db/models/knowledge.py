"""Knowledge base: sources, documents, revisions, chunks and portable vectors."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType


class KnowledgeSource(UUIDPrimaryKey, Timestamps, Base):
    """Where documents come from: user uploads, a web page, or a connector.

    Connectors (e.g. government knowledge, ROADMAP Phase 7) are not implemented yet.
    """

    __tablename__ = "knowledge_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # upload | url | connector
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class KnowledgeDocument(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (Index("ix_knowledge_documents_user_hash", "user_id", "content_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A StorageProvider key, never a filesystem path.
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    # queued | processing | indexed | partial | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class DocumentRevision(UUIDPrimaryKey, Base):
    """One version of a document's content. Never overwritten."""

    __tablename__ = "document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class KnowledgeChunk(UUIDPrimaryKey, Base):
    """A searchable piece of one revision. Its vector lives in the VectorStore."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_revision_index", "revision_id", "chunk_index"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class VectorEntry(UUIDPrimaryKey, Base):
    """Portable embedding storage used by LocalVectorStore (SQLite or PostgreSQL
    without pgvector). PgVectorStore keeps its vectors in `pgvector_entries`."""

    __tablename__ = "vector_entries"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "model"),
        Index("ix_vector_entries_scope", "user_id", "owner_type", "model"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)  # chunk | memory
    owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class OcrPage(UUIDPrimaryKey, Base):
    """Text read by OCR from one page of a stored file, with its provenance: the lines
    and their coordinates, the language packs, the engine's own confidence, and what was
    done to the page image. Replaced when the document is OCR'd again."""

    __tablename__ = "ocr_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    languages: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    script: Mapped[str | None] = mapped_column(String(30), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False)  # tesseract
    engine_version: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    """Mean engine word confidence (0-100). Not a calibrated accuracy."""
    rotation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deskew_angle: Mapped[float] = mapped_column(default=0.0, nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """Hash of the stored file the page came from."""
    page_image_sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LongDocPart(UUIDPrimaryKey, Base):
    """The result of one model call on one part of a long document (a part summary, a
    translated part...). Keyed by the part's content hash and the task, so a long job
    that stopped half-way continues where it stopped and unchanged parts are reused."""

    __tablename__ = "long_doc_parts"
    __table_args__ = (UniqueConstraint("user_id", "task", "part_sha256"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task: Mapped[str] = mapped_column(String(120), nullable=False)
    part_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    part_index: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
