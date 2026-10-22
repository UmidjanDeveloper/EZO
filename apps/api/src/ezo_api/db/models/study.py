"""Source-bound cards and immutable, idempotent self-reported recall events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType


class StudyCard(UUIDPrimaryKey, Base):
    __tablename__ = "study_cards"
    __table_args__ = (
        Index("ix_study_cards_user_due", "user_id", "due_at"),
        CheckConstraint("version >= 0 AND interval_days >= 0", name="schedule"),
        CheckConstraint("quote_start >= 0 AND quote_end > quote_start", name="quote"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE")
    )
    # Chunk IDs may disappear on reindex; provenance remains revision + offsets.
    chunk_id: Mapped[uuid.UUID] = mapped_column()
    front: Mapped[str] = mapped_column(String(600))
    back: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    quote_start: Mapped[int] = mapped_column(Integer)
    quote_end: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class StudyReview(UUIDPrimaryKey, Base):
    __tablename__ = "study_reviews"
    __table_args__ = (UniqueConstraint("card_id", "event_id"),)

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_cards.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column()
    expected_version: Mapped[int] = mapped_column(Integer)
    rating: Mapped[str] = mapped_column(String(8))
    result: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
