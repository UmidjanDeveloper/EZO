"""Skills: small tools EZO writes for its owner, run only after the owner approved the exact
code, and only inside a locked container (no network, read-only, small limits).

A `Skill` holds its current code and the hash the owner approved. Changing the code clears
the approval. A `SkillRun` is one execution request: the API queues it; a separate skill
worker (the only process with Docker access) runs it and stores the result.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType

SKILL_STATUSES = ("draft", "approved", "disabled")
RUN_STATUSES = ("queued", "running", "completed", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class Skill(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint(_in("status", SKILL_STATUSES), name="status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_hint: Mapped[str] = mapped_column(Text, default="", nullable=False)
    """What `run(data)` expects, in words and an example (for the model that fills it)."""
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    approved_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    checks: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class SkillRun(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "skill_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        Index("ix_skill_runs_status_created", "status", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    """The approved code this run executes (checked again by the worker)."""
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    output: Mapped[Any] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
