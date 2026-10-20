"""Durable orchestration and immutable processing publications, not native workers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType


class DocumentJob(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "document_jobs"
    __table_args__ = (
        UniqueConstraint("document_id", "input_revision_id", "parser_version"),
        CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')", name="state"
        ),
        CheckConstraint("attempts >= 0 AND attempts <= max_attempts", name="attempts"),
        CheckConstraint("max_attempts >= 1 AND max_attempts <= 5", name="retry_bound"),
        CheckConstraint(
            "(state = 'running' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (state != 'running' AND lease_expires_at IS NULL)",
            name="lease",
        ),
        Index("ix_document_jobs_claim", "state", "available_at"),
        Index("ix_document_jobs_lease", "state", "lease_expires_at"),
        Index("ix_document_jobs_scope", "user_id", "project_id", "id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    input_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE")
    )
    input_content_hash: Mapped[str] = mapped_column(String(64))
    input_text_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(200), nullable=True)


class DocumentJobPublication(UUIDPrimaryKey, Base):
    """A processing revision; append only through the fenced publication service.

    Does not replace KnowledgeDocument.current_revision_id or change K2 search.
    """

    __tablename__ = "document_job_publications"
    __table_args__ = (UniqueConstraint("job_id"),)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_jobs.id", ondelete="CASCADE"))
    input_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE")
    )
    parser_version: Mapped[str] = mapped_column(String(80))
    normalized_text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    result_sha256: Mapped[str] = mapped_column(String(64))
    spans: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
