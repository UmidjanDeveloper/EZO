"""Immutable, bounded raw revisions for the separate Student executor worker."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ezo_api.db.base import Base


class StudentRawRevision(Base):
    __tablename__ = "student_raw_revisions"
    __table_args__ = (
        CheckConstraint("length(data) > 0 AND length(data) <= 5242880", name="size"),
        CheckConstraint("format IN ('pdf','docx','epub','png','jpeg')", name="format"),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[bytes] = mapped_column(LargeBinary)
    format: Mapped[str] = mapped_column(String(8))
    sha256: Mapped[str] = mapped_column(String(64))
