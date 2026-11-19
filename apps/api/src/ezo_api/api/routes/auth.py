"""Password sign-in for owner-invited accounts (EZO_AUTH_MODE=token).

- POST /api/auth/invite          {code}            → whose invite it is (email, name)
- POST /api/auth/accept-invite   {code, password}  → sets the password, signs in
- POST /api/auth/login           {email, password} → signs in
- POST /api/auth/logout                            → revokes this sign-in

Signing in issues a normal per-user token (30 days), stored only as SHA-256. These three
public routes are rate limited per address and per account; wrong answers all look alike.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep
from ezo_api.auth.local import USER_TOKEN_PREFIX, token_hash
from ezo_api.auth.passwords import PasswordError, check_strength, hash_password, verify_password
from ezo_api.db.base import utcnow
from ezo_api.db.models import User, UserInvite, UserToken
from ezo_api.security.audit import audit
from ezo_api.security.rate_limit import RateLimitExceededError

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_DAYS = 30
PER_MINUTE = 10


class CodeIn(BaseModel):
    code: str = Field(min_length=10, max_length=200)


class AcceptIn(CodeIn):
    password: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


def _limit(services: ServicesDep, request: Request, *keys: str) -> None:
    address = request.client.host if request.client else "unknown"
    try:
        for key in (f"auth-ip:{address}", *keys):
            services.rate_limiter.check(key, PER_MINUTE)
    except RateLimitExceededError as exc:
        raise HTTPException(
            429,
            detail={
                "code": "rate_limited",
                "message": f"Too many attempts. Try again in {exc.retry_after_seconds} seconds.",
            },
        ) from exc


def _token_mode(services: ServicesDep) -> None:
    if services.settings.auth_mode != "token":
        raise HTTPException(
            409, detail={"code": "local_mode", "message": "Sign-in is used only in token mode."}
        )


async def _invite(session: SessionDep, code: str) -> UserInvite:
    invite = await session.scalar(
        select(UserInvite).where(UserInvite.code_sha256 == token_hash(code))
    )
    if (
        invite is None
        or invite.used_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= utcnow()
    ):
        raise HTTPException(
            404,
            detail={"code": "invite_invalid", "message": "The invite link is invalid or expired."},
        )
    return invite


async def _sign_in(session: SessionDep, user: User, label: str) -> dict[str, Any]:
    secret = USER_TOKEN_PREFIX + secrets.token_urlsafe(32)
    session.add(
        UserToken(
            user_id=user.id,
            token_sha256=token_hash(secret),
            label=label,
            expires_at=utcnow() + timedelta(days=SESSION_DAYS),
        )
    )
    await session.flush()
    return {
        "token": secret,
        "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name},
    }


@router.post("/invite")
async def invite_info(
    body: CodeIn, request: Request, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    _token_mode(services)
    _limit(services, request)
    invite = await _invite(session, body.code)
    user = await session.get(User, invite.user_id)
    assert user is not None
    return {
        "email": user.email,
        "display_name": user.display_name,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/accept-invite")
async def accept_invite(
    body: AcceptIn, request: Request, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    _token_mode(services)
    _limit(services, request)
    invite = await _invite(session, body.code)
    try:
        check_strength(body.password)
    except PasswordError as exc:
        raise HTTPException(422, detail={"code": "weak_password", "message": str(exc)}) from exc
    user = await session.get(User, invite.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            404,
            detail={"code": "invite_invalid", "message": "The invite link is invalid or expired."},
        )
    invite.used_at = utcnow()
    user.password_hash = hash_password(body.password)
    signed = await _sign_in(session, user, "Veb (taklif)")
    audit(session, user.id, "account.invite_accepted", "user", user.id, {})
    await session.commit()
    return signed


@router.post("/login")
async def login(
    body: LoginIn, request: Request, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    _token_mode(services)
    email = body.email.strip().lower()
    _limit(services, request, f"auth-email:{email}")
    user = await session.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not ok or user.status != "active":
        raise HTTPException(
            401, detail={"code": "login_failed", "message": "Wrong email or password."}
        )
    signed = await _sign_in(session, user, "Veb (parol)")
    audit(session, user.id, "account.login", "user", user.id, {})
    await session.commit()
    return signed


@router.post("/logout", status_code=204)
async def logout(request: Request, user: CurrentUser, session: SessionDep) -> None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip().startswith(USER_TOKEN_PREFIX):
        row = await session.scalar(
            select(UserToken).where(UserToken.token_sha256 == token_hash(token.strip()))
        )
        if row is not None and row.user_id == user.id and row.revoked_at is None:
            row.revoked_at = utcnow()
            await session.commit()
