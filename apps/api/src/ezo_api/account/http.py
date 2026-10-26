"""HTTP mapping of quota checks: a 429 with a fixed, explainable body."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.account.entitlements import Quota, QuotaExceeded, consume_quota
from ezo_api.api.deps import CurrentUser, ServicesDep
from ezo_api.db.models import User


async def enforce_quota(
    session: AsyncSession, user: User, quota: Quota, *, owner_email: str
) -> None:
    """Count one use and commit it at once, so a later failure cannot hand it back."""
    try:
        await consume_quota(session, user, quota, owner_email=owner_email)
    except QuotaExceeded as exc:
        raise HTTPException(
            429,
            detail={
                "code": "quota_exceeded",
                "message": (
                    f"Kunlik limit tugadi ({exc.limit}, tarif: {exc.tier}). "
                    "Ertaga qayta urinib ko‘ring."
                ),
                "quota": exc.quota,
                "limit": exc.limit,
                "tier": exc.tier,
            },
        ) from exc
    await session.commit()


def require_quota(quota: Quota) -> Callable[[CurrentUser, ServicesDep], Awaitable[None]]:
    """Route dependency: count one use of `quota` in its own committed transaction."""

    async def dependency(user: CurrentUser, services: ServicesDep) -> None:
        async with services.db.sessionmaker() as session:
            account = await session.get(User, user.id)
            if account is not None:
                await enforce_quota(
                    session, account, quota, owner_email=services.settings.owner_email
                )

    return dependency
