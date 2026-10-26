"""Owner-managed accounts (P8 foundation): users, per-user tokens, tiers and usage.

No self-signup and no billing. Only the Super Admin manages accounts; a tier never
grants authority and roles cannot be changed here (see `ezo_api.owner_admin`).
Tokens are random, shown once, stored only as SHA-256 and revocable.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ezo_api.account.entitlements import unlimited, usage
from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, SuperAdminUser, rate_limit
from ezo_api.auth.local import USER_TOKEN_PREFIX, token_hash
from ezo_api.db.base import utcnow
from ezo_api.db.models import User, UserToken
from ezo_api.security.audit import audit

router = APIRouter(tags=["accounts"], dependencies=[Depends(rate_limit("default"))])

MAX_TOKENS_PER_USER = 10


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=200)
    tier: Literal["free", "pro", "premium"] = "free"


class UserUpdate(BaseModel):
    tier: Literal["free", "pro", "premium"] | None = None
    status: Literal["active", "disabled"] | None = None


class TokenCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


def _user_out(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "tier": user.tier,
        "status": user.status,
    }


def _token_out(token: UserToken) -> dict[str, Any]:
    return {
        "id": str(token.id),
        "label": token.label,
        "created_at": token.created_at.isoformat(),
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "revoked": token.revoked_at is not None,
    }


async def _managed(session: SessionDep, admin: User, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, detail="User not found.")
    if user.id == admin.id:
        raise HTTPException(409, detail="Manage your own owner account offline (owner_admin).")
    return user


@router.get("/api/account/usage")
async def my_usage(user: CurrentUser, session: SessionDep, services: ServicesDep) -> dict[str, Any]:
    """The caller's tier and today's counted usage (server-side numbers)."""
    owner_email = services.settings.owner_email
    counted = await usage(session, user, owner_email=owner_email)
    return {
        "tier": user.tier,
        "unlimited": unlimited(user, owner_email),
        "usage": [{"quota": u.quota, "used": u.used, "limit": u.limit} for u in counted],
    }


@router.get("/api/admin/users")
async def list_users(admin: SuperAdminUser, session: SessionDep) -> list[dict[str, Any]]:
    users = (await session.scalars(select(User).order_by(User.created_at))).all()
    return [_user_out(u) for u in users]


@router.post("/api/admin/users", status_code=201)
async def create_user(
    body: UserCreate, admin: SuperAdminUser, session: SessionDep
) -> dict[str, Any]:
    user = User(
        email=body.email.lower(),
        display_name=body.display_name,
        tier=body.tier,
        role="user",
        status="active",
        preferences={},
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, detail="An account with this email already exists.") from exc
    audit(session, admin.id, "account.user_created", "user", user.id, {"tier": body.tier})
    await session.commit()
    return _user_out(user)


@router.patch("/api/admin/users/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, admin: SuperAdminUser, session: SessionDep
) -> dict[str, Any]:
    user = await _managed(session, admin, user_id)
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    if body.status == "disabled":
        # Disabling also revokes every token, so nothing keeps working on the side.
        for token in (
            await session.scalars(
                select(UserToken).where(
                    UserToken.user_id == user.id, UserToken.revoked_at.is_(None)
                )
            )
        ).all():
            token.revoked_at = utcnow()
    audit(session, admin.id, "account.user_updated", "user", user.id, changes)
    await session.commit()
    return _user_out(user)


@router.post("/api/admin/users/{user_id}/tokens", status_code=201)
async def issue_token(
    user_id: uuid.UUID, body: TokenCreate, admin: SuperAdminUser, session: SessionDep
) -> dict[str, Any]:
    user = await _managed(session, admin, user_id)
    if user.status != "active":
        raise HTTPException(409, detail="The account is disabled.")
    active = (
        await session.scalars(
            select(UserToken).where(UserToken.user_id == user.id, UserToken.revoked_at.is_(None))
        )
    ).all()
    if len(active) >= MAX_TOKENS_PER_USER:
        raise HTTPException(409, detail="Too many active tokens; revoke one first.")
    secret = USER_TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = UserToken(
        user_id=user.id,
        token_sha256=token_hash(secret),
        label=body.label,
        expires_at=utcnow() + timedelta(days=body.expires_in_days)
        if body.expires_in_days
        else None,
    )
    session.add(token)
    await session.flush()
    audit(session, admin.id, "account.token_issued", "user", user.id, {"label": body.label})
    await session.commit()
    # The only time the secret is ever shown; it is not stored.
    return {"token": secret, **_token_out(token)}


@router.get("/api/admin/users/{user_id}/tokens")
async def list_tokens(
    user_id: uuid.UUID, admin: SuperAdminUser, session: SessionDep
) -> list[dict[str, Any]]:
    user = await _managed(session, admin, user_id)
    tokens = (
        await session.scalars(
            select(UserToken).where(UserToken.user_id == user.id).order_by(UserToken.created_at)
        )
    ).all()
    return [_token_out(t) for t in tokens]


@router.delete("/api/admin/users/{user_id}/tokens/{token_id}")
async def revoke_token(
    user_id: uuid.UUID, token_id: uuid.UUID, admin: SuperAdminUser, session: SessionDep
) -> dict[str, Any]:
    user = await _managed(session, admin, user_id)
    token = await session.get(UserToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(404, detail="Token not found.")
    token.revoked_at = token.revoked_at or utcnow()
    audit(session, admin.id, "account.token_revoked", "user", user.id, {"token": str(token.id)})
    await session.commit()
    return _token_out(token)
