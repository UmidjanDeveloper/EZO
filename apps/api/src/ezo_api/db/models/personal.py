from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType


class PersonalGoal(UUIDPrimaryKey, Timestamps, Base):
    """A user's personal or learning goal.

    Goals allow tracking progress across learning, language, career,
    productivity, and personal milestones.
    """

    __tablename__ = "personal_goals"
    __table_args__ = (Index("ix_personal_goals_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="learning", nullable=False)
    target_date: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # active, completed, paused, archived
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0.0 - 1.0
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
