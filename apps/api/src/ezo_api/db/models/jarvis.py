"""JARVIS durable governed tasks: paired devices, tasks, steps, approvals, recipients.

Nothing here is an execution authority by itself. A step runs only through the fixed
action registry in `ezo_api.jarvis`, and any external effect needs an approval bound
to the exact action parameters (`scope_sha256`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType

TASK_STATES = ("queued", "awaiting_authorization", "running", "completed", "failed", "cancelled")
PLATFORMS = ("windows", "android", "linux", "chrome")
STEP_STATES = (
    "pending",
    "awaiting_authorization",
    "awaiting_device",
    "running",
    "completed",
    "failed",
    "cancelled",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class JarvisDevice(UUIDPrimaryKey, Timestamps, Base):
    """A companion app that proved possession of its Ed25519 key and was confirmed by the
    owner with the code it displayed. `pending` devices can do nothing."""

    __tablename__ = "jarvis_devices"
    __table_args__ = (
        CheckConstraint(_in("status", ("pending", "paired", "revoked")), name="status"),
        CheckConstraint(_in("platform", PLATFORMS), name="platform"),
        UniqueConstraint("public_key"),
        Index("ix_jarvis_devices_user", "user_id", "status"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(16))
    public_key: Mapped[str] = mapped_column(String(64))
    """Ed25519 public key, hex."""
    status: Mapped[str] = mapped_column(String(16), default="pending")
    code_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    confirm_attempts: Mapped[int] = mapped_column(default=0)
    capabilities: Mapped[list[str]] = mapped_column(JSONType, default=list)
    paired_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class JarvisTask(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "jarvis_tasks"
    __table_args__ = (
        CheckConstraint(_in("state", TASK_STATES), name="state"),
        UniqueConstraint("user_id", "idempotency_key"),
        Index("ix_jarvis_tasks_user", "user_id", "created_at"),
        Index("ix_jarvis_tasks_runnable", "state"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jarvis_devices.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40))
    request_text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(2), default="uz")
    state: Mapped[str] = mapped_column(String(24), default="queued")
    plan: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    """The validated, parsed request (never model text) the steps were built from."""
    report: Mapped[str] = mapped_column(Text, default="")
    """Truthful final summary built by EZO from step outcomes."""
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class JarvisTaskStep(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "jarvis_task_steps"
    __table_args__ = (
        CheckConstraint(_in("state", STEP_STATES), name="state"),
        UniqueConstraint("task_id", "position"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jarvis_tasks.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(48))
    state: Mapped[str] = mapped_column(String(24), default="pending")
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    """Provider/device evidence (e.g. Telegram message_id). Never invented."""
    scope_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Hash of the exact external action an approval must match."""
    device_request_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    device_request_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class JarvisAuthorization(UUIDPrimaryKey, Base):
    """The owner's decision on one exact external action (hash-bound, single use)."""

    __tablename__ = "jarvis_authorizations"
    __table_args__ = (
        CheckConstraint(_in("decision", ("approved", "rejected")), name="decision"),
        UniqueConstraint("step_id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jarvis_tasks.id", ondelete="CASCADE"))
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jarvis_task_steps.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(48))
    scope_sha256: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class TelegramRecipient(UUIDPrimaryKey, Timestamps, Base):
    """A person who started EZO's Telegram bot with a one-time link code.

    Telegram bots can only message chats that started them; EZO never guesses a chat.
    """

    __tablename__ = "telegram_recipients"
    __table_args__ = (
        UniqueConstraint("user_id", "label"),
        CheckConstraint(_in("status", ("pending", "verified", "revoked")), name="status"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(60))
    """How the owner names this person (e.g. "Baxtiyor"); matched case-insensitively."""
    status: Mapped[str] = mapped_column(String(16), default="pending")
    link_code_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    link_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
