"""Authentication abstraction.

`AuthBackend` turns an HTTP request into a `User`. Milestone 1 ships a
single-owner backend suitable for a personal, locally-run EZO. Multi-user
backends (sessions, OAuth) can be added later without touching routes, which
only depend on `get_current_user`.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import User


class AuthError(Exception):
    """Authentication failed; maps to HTTP 401."""


class AuthBackend(Protocol):
    async def authenticate(self, request: Request, session: AsyncSession) -> User: ...
