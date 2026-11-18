"""District center: the projects a district runs (xatlov, bandlik, …), the people
responsible for them, their progress and the warnings sent to them.

Everything belongs to one EZO account (the hokimiyat's owner account). Progress comes from
an official API, an Excel/CSV import or manual entry, and every value keeps its source.
A `DistrictNotice` is a warning to one person; it is sent only after a person with the
right to approve pressed "Send", and each channel's real delivery result is stored.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType

PROJECT_STATUSES = ("active", "paused", "finished")
SOURCE_KINDS = ("manual", "import", "api")
NOTICE_STATUSES = ("draft", "sent", "partly_sent", "failed", "cancelled")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class DistrictProject(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "district_projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint(_in("status", PROJECT_STATUSES), name="status"),
        CheckConstraint(_in("source_kind", SOURCE_KINDS), name="source_kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    """"Xatlov 2026"; chat questions find a project by the words of its name and aliases."""
    aliases: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    unit: Mapped[str] = mapped_column(String(40), default="ta", nullable=False)
    """What is counted ("xonadon", "ish o'rni", "ta")."""
    responsible_org: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    """Who runs it ("Xatirchi tumani bandlik bo'limi")."""
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    """For "api": url, token_env, items_path and the field mapping (no secret values)."""
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DistrictMember(UUIDPrimaryKey, Timestamps, Base):
    """A person responsible for work in the district (mahalla raisi, inspektor, …)."""

    __tablename__ = "district_members"
    __table_args__ = (Index("ix_district_members_user_name", "user_id", "full_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    area: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    """Mahalla or sector."""
    phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """998XXXXXXXXX, for SMS."""
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    """The person's id in the official system (to match API records)."""
    telegram_recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("telegram_recipients.id", ondelete="SET NULL"), nullable=True
    )


class DistrictAssignment(UUIDPrimaryKey, Timestamps, Base):
    """One person's share of one project: plan and the latest done count."""

    __tablename__ = "district_assignments"
    __table_args__ = (UniqueConstraint("project_id", "member_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("district_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("district_members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    done: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    reported_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class DistrictProgress(UUIDPrimaryKey, Base):
    """History of done counts (one row per change), for trends and "what changed"."""

    __tablename__ = "district_progress"
    __table_args__ = (
        Index("ix_district_progress_assignment_time", "assignment_id", "recorded_at"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("district_assignments.id", ondelete="CASCADE"), nullable=False
    )
    done: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class DistrictNotice(UUIDPrimaryKey, Timestamps, Base):
    """A warning to one person. Drafts change nothing outside EZO."""

    __tablename__ = "district_notices"
    __table_args__ = (
        CheckConstraint(_in("status", NOTICE_STATUSES), name="status"),
        Index("ix_district_notices_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("district_projects.id", ondelete="SET NULL"), nullable=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("district_members.id", ondelete="SET NULL"), nullable=True
    )
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    sender: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    """Whose name the message carries ("Xatirchi tumani hokimi")."""
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    """Per channel: {"ok": bool, "id"?: provider message id, "error"?: reason}."""
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
