from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, utcnow
from ezo_api.db.models.types import JSONType


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("tier IN ('free','pro','premium')", name="tier"),
        CheckConstraint("status IN ('active','disabled')", name="status"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default="free", server_default="free")
    """Entitlement tier for quotas. Never grants authority (see require_super_admin)."""
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")


class UserToken(UUIDPrimaryKey, Base):
    """A per-user API token issued by the Super Admin. Only its SHA-256 is stored."""

    __tablename__ = "user_tokens"
    __table_args__ = (Index("ix_user_tokens_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class UsageEvent(UUIDPrimaryKey, Base):
    """One counted use of a quota. Kept apart from the content so deleting a
    conversation or a document never gives the quota back."""

    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_user_quota_time", "user_id", "quota", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    quota: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
