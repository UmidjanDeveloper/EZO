"""Devonxona (the hokimiyat's office): citizens' appeals, meetings and the tasks they give.

Rows belong to one EZO account. Deadlines are dates (the district's calendar); "overdue" is
computed, never stored, so it is always true to today's date.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey

APPEAL_STATUSES = ("new", "in_progress", "answered", "closed")
APPEAL_CHANNELS = ("virtual_reception", "president_portal", "written", "oral", "phone", "other")
TASK_STATUSES = ("open", "done", "cancelled")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class Appeal(UUIDPrimaryKey, Timestamps, Base):
    """A citizen's or organisation's appeal (murojaat) and its handling."""

    __tablename__ = "gov_appeals"
    __table_args__ = (
        UniqueConstraint("user_id", "number"),
        CheckConstraint(_in("status", APPEAL_STATUSES), name="status"),
        CheckConstraint(_in("channel", APPEAL_CHANNELS), name="channel"),
        Index("ix_gov_appeals_user_due", "user_id", "due_on"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    """"M-2026-0001", per account and year."""
    applicant: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    """Address or phone as the applicant gave it."""
    channel: Mapped[str] = mapped_column(String(24), default="other", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("district_members.id", ondelete="SET NULL"), nullable=True
    )
    assignee_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    answered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    answer_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )


class Meeting(UUIDPrimaryKey, Timestamps, Base):
    """A meeting (yig'ilish) and its minutes."""

    __tablename__ = "gov_meetings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    held_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    """The raw notes the minutes were made from."""
    minutes_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )


class GovTask(UUIDPrimaryKey, Timestamps, Base):
    """A task (topshiriq) given to someone, usually at a meeting."""

    __tablename__ = "gov_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "number"),
        CheckConstraint(_in("status", TASK_STATUSES), name="status"),
        Index("ix_gov_tasks_user_due", "user_id", "due_on"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    """"T-2026-0001", per account and year."""
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("gov_meetings.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("district_members.id", ondelete="SET NULL"), nullable=True
    )
    assignee_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
