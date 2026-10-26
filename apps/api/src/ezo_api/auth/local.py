"""Authentication for a personal EZO installation, with owner-managed extra accounts.

- mode "local": every request acts as the owner (fine on your own computer). Per-user
  tokens are not used in this mode.
- mode "token": requests must send `Authorization: Bearer <token>`:
  * the installation token (`EZO_API_TOKEN`) acts as the owner;
  * a per-user token (`ezo_u_…`, issued by the Super Admin, stored only as SHA-256)
    acts as that user while it is unexpired, unrevoked and the account is active.
  Every route already scopes data by the authenticated user's id.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.auth.base import AuthError
from ezo_api.db.base import utcnow
from ezo_api.db.models import User, UserToken

USER_TOKEN_PREFIX = "ezo_u_"  # noqa: S105 - a public prefix, not a secret
_LAST_USED_RESOLUTION = timedelta(minutes=5)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _bearer(request_or_header: Request | str) -> str | None:
    header = (
        request_or_header
        if isinstance(request_or_header, str)
        else request_or_header.headers.get("authorization", "")
    )
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def user_for_token(session: AsyncSession, token: str) -> User | None:
    """The active user a per-user token belongs to, or None (constant-time hash lookup)."""
    if not token.startswith(USER_TOKEN_PREFIX) or len(token) > 200:
        return None
    row = await session.scalar(select(UserToken).where(UserToken.token_sha256 == token_hash(token)))
    now = utcnow()
    if row is None or row.revoked_at is not None or (row.expires_at and row.expires_at <= now):
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    if row.last_used_at is None or now - row.last_used_at > _LAST_USED_RESOLUTION:
        row.last_used_at = now
        await session.commit()
    return user


class LocalOwnerAuth:
    def __init__(
        self, owner_email: str, owner_name: str, required_token: str | None = None
    ) -> None:
        self.owner_email = owner_email.lower()
        self.owner_name = owner_name
        self.required_token = required_token

    def is_owner_token(self, token: str | None) -> bool:
        return (
            self.required_token is not None
            and token is not None
            and hmac.compare_digest(token.encode(), self.required_token.encode())
        )

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
        if self.required_token is None:
            return await self.ensure_owner(session)
        token = _bearer(request)
        if self.is_owner_token(token):
            return await self.ensure_owner(session)
        user = await user_for_token(session, token) if token else None
        if user is None:
            raise AuthError("Missing or invalid API token.")
        return user
