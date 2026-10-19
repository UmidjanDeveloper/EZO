"""Knowledge OS: named knowledge libraries and the sources EZO learned from.

A learned source is registry metadata (what the source is, its version, licence, limits,
status and what happened while reading it). Its documents are ordinary knowledge
documents under one `KnowledgeSource`, so retrieval, citations and deletion are shared
with the rest of the knowledge base.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType


class KnowledgeLibrary(UUIDPrimaryKey, Timestamps, Base):
    """A named collection of learned sources ("Python kutubxonalari", "Universitet nizomlari")."""

    __tablename__ = "knowledge_libraries"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_knowledge_libraries_user_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class LearnedSource(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "learned_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    library_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_libraries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    knowledge_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    """website | github | pypi | npm"""
    target: Mapped[str] = mapped_column(String(1000), nullable=False)
    """Canonical URL or identifier (https://…, github:owner/repo, pypi:name, npm:name)."""
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    """queued | inspecting | reading | indexing | indexed | partial | failed"""
    version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    license: Mapped[str | None] = mapped_column(String(200), nullable=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    """What discovery found: publisher, description, links, structure, licence review…"""
    limits: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    security_flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Hash over the documents read, to notice changes on a later refresh."""
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
