"""Terminology memory for translation: the user's own term pairs.

A term belongs to one user and, optionally, to one of their organization profiles
(organization-specific vocabulary). EZO only stores what the user entered.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UUIDPrimaryKey


class GlossaryTerm(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "glossary_terms"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_profiles.id", ondelete="CASCADE"), index=True, nullable=True
    )
    source_language: Mapped[str] = mapped_column(String(10), nullable=False)
    """uz | ru | en (Uzbek terms are stored as entered, in either script)"""
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    source_term: Mapped[str] = mapped_column(String(300), nullable=False)
    target_term: Mapped[str] = mapped_column(String(300), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
