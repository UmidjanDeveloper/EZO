"""FastAPI dependencies shared by routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import User
from ezo_api.security.edge import AUTHENTICATED
from ezo_api.services import Services


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_session(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    async with services.db.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, services: ServicesDep, session: SessionDep) -> User:
    return await services.auth.authenticate(request, session)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_super_admin(user: CurrentUser) -> User:
    """Strict authorization: only a user with role='super_admin' can access governance endpoints.

    Subscription status (e.g. pro, enterprise) NEVER grants super_admin privilege.
    """
    from fastapi import HTTPException

    if getattr(user, "role", "user") != "super_admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": "Super Admin privileges required. Subscription status does not grant governance access.",
            },
        )
    return user


SuperAdminUser = Annotated[User, Depends(require_super_admin)]


def client_key(request: Request) -> str:
    """Who the limit applies to. With token auth the edge guard has already checked the
    token, so every request here is the owner's (one shared key: an attacker can neither
    use up nor dodge it). Without token auth (own computer) the client address is used."""
    if request.scope.get("state", {}).get(AUTHENTICATED):
        return "owner"
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str) -> Callable[[Request, Services], Awaitable[None]]:
    """Dependency factory: limit requests per client for a bucket ("chat" or "default")."""

    async def dependency(request: Request, services: ServicesDep) -> None:
        settings = services.settings
        limit = (
            settings.rate_limit_chat_per_minute
            if bucket == "chat"
            else settings.rate_limit_default_per_minute
        )
        key = f"{bucket}:{client_key(request)}"
        services.rate_limiter.check(key, limit)
        if bucket == "chat":
            # Calls that may reach a paid AI provider also have a daily cap (cost control).
            services.daily_limiter.check(key, settings.rate_limit_chat_per_day)

    return dependency
