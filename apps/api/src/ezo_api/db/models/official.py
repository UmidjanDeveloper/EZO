"""Official knowledge sources: legal documents, their revisions and sync runs.

A `LegalDocument` is one act from an official source (e.g. LEX.UZ) in one language.
Its text lives in the normal knowledge base (a `KnowledgeDocument` with revisions,
chunks and vectors), so hybrid search and citation checks work unchanged; this
table adds what legal answers need: number, authority, dates, status and when that
status was last verified.

Nothing here is ever overwritten silently: a changed text becomes a new
`LegalRevision` (the old one and its knowledge revision are kept).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType

LEGAL_STATUSES = ("in_force", "amended", "repealed", "expired", "not_yet_in_force", "unknown")
"""`unknown` unless the source itself states the status."""
STATUS_SOURCES = ("source_text", "unverified")
SYNC_STATUSES = ("running", "completed", "partial", "failed", "blocked", "interrupted")


class LegalDocument(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "connector", "source_doc_id", "language"),
        Index("ix_legal_documents_hash", "user_id", "content_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    connector: Mapped[str] = mapped_column(String(40), nullable=False)
    source_doc_id: Mapped[str] = mapped_column(String(100), nullable=False)
    """The source's own stable identifier (e.g. the LEX.UZ document number in the URL)."""
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    script: Mapped[str | None] = mapped_column(String(10), nullable=True)  # latn | cyrl
    knowledge_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    authority: Mapped[str | None] = mapped_column(String(300), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    adopted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False)
    status_source: Mapped[str] = mapped_column(String(20), default="unverified", nullable=False)
    status_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_revisions.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    last_retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    """Last time the official text was fetched successfully."""
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_documents.id", ondelete="SET NULL"), nullable=True
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class LegalRevision(UUIDPrimaryKey, Base):
    """One retrieved version of a legal document's text. Never modified or deleted by sync."""

    __tablename__ = "legal_revisions"
    __table_args__ = (UniqueConstraint("legal_document_id", "revision_number"),)

    legal_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    """The source's own edition marker, when it shows one (never invented)."""
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """The fetched page exactly as received (provenance)."""
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class OfficialSyncRun(UUIDPrimaryKey, Base):
    """One synchronization run; the cursor makes an interrupted run resumable."""

    __tablename__ = "official_sync_runs"
    __table_args__ = (Index("ix_official_sync_runs_user_connector", "user_id", "connector"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    connector: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    requested: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    done: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(JSONType, default=dict, nullable=False)
    requests_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resumed_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("official_sync_runs.id", ondelete="SET NULL"), nullable=True
    )
