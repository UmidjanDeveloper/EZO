"""Single-owner authentication for a personal EZO installation.

- mode "local": every request acts as the owner (fine on your own computer).
- mode "token": requests must send `Authorization: Bearer <EZO_API_TOKEN>`.
  Use this whenever EZO is reachable from other machines.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.auth.base import AuthError
from ezo_api.db.models import User


class LocalOwnerAuth:
    def __init__(
        self, owner_email: str, owner_name: str, required_token: str | None = None
    ) -> None:
        self.owner_email = owner_email.lower()
        self.owner_name = owner_name
        self.required_token = required_token

    def _check_token(self, request: Request) -> None:
        if self.required_token is None:
            return
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode(), self.required_token.encode()
        ):
            raise AuthError("Missing or invalid API token.")

    async def ensure_owner(self, session: AsyncSession) -> User:
        user = await session.scalar(select(User).where(User.email == self.owner_email))
        if user is not None:
            return user
        user = User(email=self.owner_email, display_name=self.owner_name, preferences={})
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            # Another request created the owner concurrently.
            await session.rollback()
            existing = await session.scalar(select(User).where(User.email == self.owner_email))
            if existing is None:
                raise
            return existing
        return user

    async def authenticate(self, request: Request, session: AsyncSession) -> User:
        self._check_token(request)
        return await self.ensure_owner(session)
