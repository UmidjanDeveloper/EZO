from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType


class Memory(UUIDPrimaryKey, Timestamps, Base):
    """A long-term memory item.

    memory_type is `profile` (stable facts/preferences about the user) or
    `project` (facts and decisions that belong to one project). Conversation
    memory is the message history itself and is not duplicated here.
    """

    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="other", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding vectors arrive with the VectorStore in Milestone 2. Stored as a
    # JSON list so the schema is portable; the vector index lives in the store.
    embedding: Mapped[list[float] | None] = mapped_column(JSONType, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)  # auto | user
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_accessed: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
