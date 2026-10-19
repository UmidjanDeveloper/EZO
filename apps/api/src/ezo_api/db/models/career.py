"""Career profile: the facts a CV and application letters are built from.

Entered by the user only. EZO never adds an employer, a date, a degree, a skill or an
achievement that is not here (or in the user's message). One profile per user.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType


class CareerProfile(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "career_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    links: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    """[{role, organization, location, start, end, achievements: [str]}]"""
    education: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    """[{institution, degree, field, start, end, notes}]"""
    skills: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    languages: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    """[{language, level}]"""
    certificates: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    """[{name, issuer, year}]"""
