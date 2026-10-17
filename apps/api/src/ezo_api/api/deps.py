"""FastAPI dependencies shared by routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import User
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


def client_key(request: Request) -> str:
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
        services.rate_limiter.check(f"{bucket}:{client_key(request)}", limit)

    return dependency
