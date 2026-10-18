"""Organization profiles: who the user writes for (letterhead, contacts, style, terms).

Everything here is entered by the user; EZO never fills it with guesses. A profile is
owned by one user (single-user today; the owner column is what a future workspace
model will attach to).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base, Timestamps, UUIDPrimaryKey
from ezo_api.db.models.types import JSONType


class OrganizationProfile(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organization_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    org_type: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    """government | university | school | company | research | nonprofit | other"""
    department: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    head_position: Mapped[str | None] = mapped_column(String(200), nullable=True)
    head_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    letterhead: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Lines printed at the top of letters, exactly as entered."""
    style_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminology: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    """Preferred terms: {"avoid": "use instead"}."""
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
