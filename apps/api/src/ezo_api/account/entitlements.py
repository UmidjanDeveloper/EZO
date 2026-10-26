"""Tier entitlements and server-side quotas (P8). No billing is connected.

Tiers only change limits; they never grant authority (Super Admin is a separate role).
The installation owner and the Super Admin have no quota. Uses are counted in their own table,
so limits hold across restarts and clients and deleting content does not reset them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import UsageEvent, User

Tier = Literal["free", "pro", "premium"]
Quota = Literal["chat_messages_per_day", "document_jobs_per_day", "jarvis_tasks_per_day"]

LIMITS: dict[Tier, dict[Quota, int]] = {
    "free": {
        "chat_messages_per_day": 50,
        "document_jobs_per_day": 5,
        "jarvis_tasks_per_day": 3,
    },
    "pro": {
        "chat_messages_per_day": 300,
        "document_jobs_per_day": 30,
        "jarvis_tasks_per_day": 20,
    },
    "premium": {
        "chat_messages_per_day": 1000,
        "document_jobs_per_day": 100,
        "jarvis_tasks_per_day": 100,
    },
}


RETENTION = timedelta(days=2)
"""Usage rows older than this are deleted; only the last 24 hours are ever counted."""


class QuotaExceeded(Exception):
    def __init__(self, quota: Quota, limit: int, tier: str) -> None:
        self.quota, self.limit, self.tier = quota, limit, tier
        super().__init__(f"Daily limit reached for {quota} ({limit} on the {tier} tier).")


@dataclass(frozen=True, slots=True)
class Usage:
    quota: Quota
    used: int
    limit: int | None


def _tier(user: User) -> Tier:
    return user.tier if user.tier in ("free", "pro", "premium") else "free"  # type: ignore[return-value]


def unlimited(user: User, owner_email: str) -> bool:
    """The installation owner (configured owner email) and the Super Admin have no quota."""
    return user.role == "super_admin" or user.email == owner_email.lower()


async def used_today(session: AsyncSession, user_id: uuid.UUID, quota: Quota) -> int:
    """Counted uses in the last 24 hours (a rolling window)."""
    since = utcnow() - timedelta(days=1)
    query = (
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user_id,
            UsageEvent.quota == quota,
            UsageEvent.created_at >= since,
        )
    )
    return int(await session.scalar(query) or 0)


async def consume_quota(
    session: AsyncSession, user: User, quota: Quota, *, owner_email: str
) -> None:
    """Refuse when the limit is reached, otherwise count this use (caller commits).

    Uses are recorded for everyone, so the Super Admin's usage is visible too. The user
    row is locked first, so on PostgreSQL concurrent requests cannot all pass the same
    count (SQLite ignores the lock; it is the single-owner development database, not a
    multi-user deployment target). Uses older than the retention window are pruned."""
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    await session.execute(
        delete(UsageEvent).where(
            UsageEvent.user_id == user.id, UsageEvent.created_at < utcnow() - RETENTION
        )
    )
    if not unlimited(user, owner_email):
        tier = _tier(user)
        limit = LIMITS[tier][quota]
        if await used_today(session, user.id, quota) >= limit:
            raise QuotaExceeded(quota, limit, tier)
    session.add(UsageEvent(user_id=user.id, quota=quota))


async def usage(session: AsyncSession, user: User, *, owner_email: str) -> list[Usage]:
    tier = _tier(user)
    free = unlimited(user, owner_email)
    return [
        Usage(q, await used_today(session, user.id, q), None if free else LIMITS[tier][q])
        for q in LIMITS[tier]
    ]
