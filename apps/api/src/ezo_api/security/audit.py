"""Audit logging for important operations."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import AuditLog

logger = logging.getLogger("ezo.audit")


def audit(
    session: AsyncSession,
    user_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Queue an audit record in the caller's transaction (committed with it)."""
    target = str(target_id) if target_id is not None else None
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target,
            details=details or {},
        )
    )
    logger.info("audit action=%s target=%s:%s user=%s", action, target_type, target, user_id)
