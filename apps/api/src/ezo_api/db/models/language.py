"""Language Coach data: practice sessions and the learner's progress over time.

A `LanguageSession` is one practice session (free conversation, IELTS-style speaking,
grammar coaching…). Every utterance is a `LanguageTurn`. When a section or session is
assessed, EZO stores `LanguageMetric` rows (computed numbers and *estimated* band scores,
each with a confidence) and the `LanguageMistake`s it found, so recurring patterns can be
practised later. `LanguageGoal` and `LanguageVocabularyItem` belong to the learner, not to
one session.

Raw audio is never stored; turns keep the transcript and the measured speaking time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType

LANGUAGE_MODES = (
    "free_conversation",
    "ielts",
    "teacher",
    "grammar",
    "vocabulary",
    "debate",
    "job_interview",
    "travel",
    "business",
)
SESSION_STATUSES = ("active", "completed", "abandoned")
CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
MISTAKE_CATEGORIES = (
    "articles",
    "verb_tense",
    "subject_verb_agreement",
    "word_order",
    "prepositions",
    "plurals",
    "word_choice",
    "repetition",
    "filler_words",
    "sentence_fragment",
    "pronunciation",
    "other",
)
PRONUNCIATION_CONFIDENCE = ("not_assessed", "transcript_assisted", "limited", "acoustic")


class LanguageSession(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "language_sessions"
    __table_args__ = (Index("ix_language_sessions_user_started", "user_id", "started_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    """The language being practised (not the interface language)."""
    cefr_target: Mapped[str | None] = mapped_column(String(2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    ielts_part: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    speaking_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    """Measured speaking time of voice turns (0 when the session was typed)."""
    user_words: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    band_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Estimated IELTS-style band range — never an official score."""
    fluency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lexical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grammar_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pronunciation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pronunciation_confidence: Mapped[str] = mapped_column(
        String(30), default="not_assessed", nullable=False
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class LanguageTurn(UUIDPrimaryKey, Base):
    __tablename__ = "language_turns"
    __table_args__ = (UniqueConstraint("session_id", "position"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("language_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # learner | coach
    text: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(10), default="text", nullable=False)
    ielts_part: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speech_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LanguageMetric(UUIDPrimaryKey, Base):
    __tablename__ = "language_metrics"
    __table_args__ = (Index("ix_language_metrics_user_name", "user_id", "name", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("language_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    scale: Mapped[str] = mapped_column(String(20), nullable=False)  # band | ratio | wpm | count
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # computed | estimated
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)  # high | medium | low
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LanguageMistake(UUIDPrimaryKey, Base):
    __tablename__ = "language_mistakes"
    __table_args__ = (Index("ix_language_mistakes_user_category", "user_id", "category"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("language_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("language_turns.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    original: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="minor", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LanguageGoal(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "language_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    target_band: Mapped[float | None] = mapped_column(Float, nullable=True)
    cefr_target: Mapped[str | None] = mapped_column(String(2), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class LanguageVocabularyItem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "language_vocabulary"
    __table_args__ = (UniqueConstraint("user_id", "language", "term"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    term: Mapped[str] = mapped_column(String(120), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    example: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("language_sessions.id", ondelete="SET NULL"), nullable=True
    )
    times_suggested: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
