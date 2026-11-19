"""Jadval: EZO's own recurring jobs (weekly report, deadline digest, district sync, LEX.UZ
re-check). A job never messages other people: it writes into EZO and, at most, to a
Telegram chat the owner chose for it (normally their own)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey

JOB_KINDS = ("weekly_report", "monthly_report", "deadline_digest", "district_sync", "lexuz_recheck")
RUN_STATUSES = ("running", "completed", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class ScheduledJob(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        CheckConstraint(_in("kind", JOB_KINDS), name="kind"),
        Index("ix_scheduled_jobs_due", "enabled", "next_run_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    weekdays: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    """ISO weekdays "1,3" (1 = Monday); empty = every day. Monthly jobs use `month_day`."""
    month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    """HH:MM in the installation's time zone (Asia/Tashkent by default)."""
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notify_recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("telegram_recipients.id", ondelete="SET NULL"), nullable=True
    )
    next_run_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    """A runner's claim; another runner may take the job only after it expires."""
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class ScheduledRun(UUIDPrimaryKey, Base):
    __tablename__ = "scheduled_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        Index("ix_scheduled_runs_job_started", "job_id", "started_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
