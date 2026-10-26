"""P8 foundation: owner-managed accounts, hashed per-user tokens, tiers and quotas.

Runs a real token-mode app: the edge guard, authentication and every route are real.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from ezo_api.db.models import User, UserToken
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider

OWNER_TOKEN = "owner-installation-token-0123456789abcdef"
OWNER = {"Authorization": f"Bearer {OWNER_TOKEN}"}


@pytest.fixture
async def token_app(database_url: str) -> AsyncIterator[FastAPI]:
    settings = make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN=OWNER_TOKEN)
    app = create_app(settings, providers={"anthropic": FakeProvider("anthropic")})
    yield app
    await app.state.services.db.dispose()


@pytest.fixture
async def api(token_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=token_app), base_url="http://t") as client:
        yield client


async def make_owner_super_admin(app: FastAPI) -> None:
    async with app.state.services.db.sessionmaker() as session, session.begin():
        owner = await session.scalar(select(User).where(User.role != "super_admin"))
        assert owner is not None
        owner.role = "super_admin"


async def new_user(api: AsyncClient, email: str, tier: str = "free") -> tuple[dict[str, Any], str]:
    created = await api.post(
        "/api/admin/users",
        headers=OWNER,
        json={"email": email, "display_name": email, "tier": tier},
    )
    assert created.status_code == 201, created.text
    token = await api.post(
        f"/api/admin/users/{created.json()['id']}/tokens", headers=OWNER, json={"label": "phone"}
    )
    assert token.status_code == 201, token.text
    secret = token.json()["token"]
    assert secret.startswith("ezo_u_")
    return created.json(), secret


async def test_only_the_super_admin_manages_accounts(api: AsyncClient, token_app: FastAPI) -> None:
    await api.get("/api/me", headers=OWNER)  # creates the owner row (role "user")
    denied = await api.post(
        "/api/admin/users", headers=OWNER, json={"email": "a@example.com", "display_name": "A"}
    )
    assert denied.status_code == 403
    await make_owner_super_admin(token_app)
    user, secret = await new_user(api, "dilnoza@example.com", tier="premium")
    member = {"Authorization": f"Bearer {secret}"}
    # A tier never grants authority.
    assert (await api.get("/api/admin/users", headers=member)).status_code == 403
    me = (await api.get("/api/me", headers=member)).json()
    assert me["email"] == "dilnoza@example.com"
    # The secret is never stored or listed.
    listed = (await api.get(f"/api/admin/users/{user['id']}/tokens", headers=OWNER)).json()
    assert listed and "token" not in listed[0]
    async with token_app.state.services.db.sessionmaker() as session:
        stored = (await session.scalars(select(UserToken))).all()
        assert all(secret not in (t.token_sha256 + t.label) for t in stored)


async def test_users_never_see_each_others_data(api: AsyncClient, token_app: FastAPI) -> None:
    await api.get("/api/me", headers=OWNER)
    await make_owner_super_admin(token_app)
    _, a_secret = await new_user(api, "a@example.com")
    _, b_secret = await new_user(api, "b@example.com")
    a = {"Authorization": f"Bearer {a_secret}"}
    b = {"Authorization": f"Bearer {b_secret}"}
    memory = await api.post("/api/memories", headers=a, json={"content": "A ning maxfiy rejasi"})
    assert memory.status_code == 201
    project = await api.post("/api/projects", headers=a, json={"name": "A loyihasi"})
    assert project.status_code == 201
    for headers in (b, OWNER):
        assert (await api.get("/api/memories", headers=headers)).json() == []
        assert all(
            p["name"] != "A loyihasi"
            for p in (await api.get("/api/projects", headers=headers)).json()
        )
        assert (
            await api.delete(f"/api/memories/{memory.json()['id']}", headers=headers)
        ).status_code == 404
    assert len((await api.get("/api/memories", headers=a)).json()) == 1


async def test_bad_revoked_expired_and_disabled_tokens_are_refused_at_the_edge(
    api: AsyncClient, token_app: FastAPI
) -> None:
    await api.get("/api/me", headers=OWNER)
    await make_owner_super_admin(token_app)
    user, secret = await new_user(api, "c@example.com")
    member = {"Authorization": f"Bearer {secret}"}
    assert (await api.get("/api/me", headers=member)).status_code == 200
    forged = {"Authorization": "Bearer ezo_u_" + "x" * 43}
    assert (await api.get("/api/me", headers=forged)).status_code == 401
    # Revoked.
    tokens = (await api.get(f"/api/admin/users/{user['id']}/tokens", headers=OWNER)).json()
    await api.delete(f"/api/admin/users/{user['id']}/tokens/{tokens[0]['id']}", headers=OWNER)
    assert (await api.get("/api/me", headers=member)).status_code == 401
    # Expired.
    _, second = await new_user(api, "d@example.com")
    async with token_app.state.services.db.sessionmaker() as session, session.begin():
        row = (
            await session.scalars(select(UserToken).where(UserToken.revoked_at.is_(None)))
        ).all()[-1]
        from datetime import timedelta

        from ezo_api.db.base import utcnow

        row.expires_at = utcnow() - timedelta(seconds=1)
    assert (
        await api.get("/api/me", headers={"Authorization": f"Bearer {second}"})
    ).status_code == 401
    # Disabled account: its tokens stop working and are revoked.
    third_user, third = await new_user(api, "e@example.com")
    await api.patch(
        f"/api/admin/users/{third_user['id']}", headers=OWNER, json={"status": "disabled"}
    )
    assert (
        await api.get("/api/me", headers={"Authorization": f"Bearer {third}"})
    ).status_code == 401
    listed = (await api.get(f"/api/admin/users/{third_user['id']}/tokens", headers=OWNER)).json()
    assert all(t["revoked"] for t in listed)
    # The owner cannot use the account routes to change their own account.
    owner_id = next(
        u["id"]
        for u in (await api.get("/api/admin/users", headers=OWNER)).json()
        if u["role"] == "super_admin"
    )
    assert (
        await api.patch(f"/api/admin/users/{owner_id}", headers=OWNER, json={"tier": "free"})
    ).status_code == 409


async def test_daily_quota_is_enforced_server_side(
    api: AsyncClient, token_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezo_api.account import entitlements

    monkeypatch.setitem(entitlements.LIMITS["free"], "chat_messages_per_day", 2)
    await api.get("/api/me", headers=OWNER)
    await make_owner_super_admin(token_app)
    _, secret = await new_user(api, "f@example.com")
    member = {"Authorization": f"Bearer {secret}"}
    conversations = []
    for _ in range(2):
        sent = await api.post("/api/chat", headers=member, json={"message": "Salom"})
        assert sent.status_code == 200
        conversations.append(sent.json()["conversation_id"])
    # Deleting the conversations does not give the quota back.
    for conversation in set(conversations):
        deleted = await api.delete(f"/api/conversations/{conversation}", headers=member)
        assert deleted.status_code == 204
    blocked = await api.post("/api/chat", headers=member, json={"message": "Salom"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "quota_exceeded"
    usage = (await api.get("/api/account/usage", headers=member)).json()
    chat = next(u for u in usage["usage"] if u["quota"] == "chat_messages_per_day")
    assert chat == {"quota": "chat_messages_per_day", "used": 2, "limit": 2}
    # The Super Admin (installation owner) has no quota.
    for _ in range(3):
        assert (
            await api.post("/api/chat", headers=OWNER, json={"message": "Salom"})
        ).status_code == 200
    assert (await api.get("/api/account/usage", headers=OWNER)).json()["unlimited"] is True


async def test_installation_owner_is_unlimited_without_the_super_admin_role(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezo_api.account import entitlements

    monkeypatch.setitem(entitlements.LIMITS["free"], "chat_messages_per_day", 1)
    me = (await api.get("/api/me", headers=OWNER)).json()
    assert me["role"] != "super_admin"
    for _ in range(3):
        sent = await api.post("/api/chat", headers=OWNER, json={"message": "Salom"})
        assert sent.status_code == 200
    usage = (await api.get("/api/account/usage", headers=OWNER)).json()
    assert usage["unlimited"] is True
    chat = next(u for u in usage["usage"] if u["quota"] == "chat_messages_per_day")
    assert chat == {"quota": "chat_messages_per_day", "used": 3, "limit": None}


async def test_each_user_has_their_own_rate_limit(database_url: str) -> None:
    settings = make_settings(
        database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN=OWNER_TOKEN, EZO_RATE_LIMIT_DEFAULT="6"
    )
    app = create_app(settings, providers={"anthropic": FakeProvider("anthropic")})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as api:
            await api.get("/api/me", headers=OWNER)
            await make_owner_super_admin(app)
            _, secret = await new_user(api, "g@example.com")
            member = {"Authorization": f"Bearer {secret}"}
            codes = [(await api.get("/api/memories", headers=member)).status_code for _ in range(8)]
            assert codes[-1] == 429
            # One user using up their budget does not lock out the owner.
            assert (await api.get("/api/memories", headers=OWNER)).status_code == 200
    finally:
        await app.state.services.db.dispose()


async def test_document_jobs_are_counted_on_every_path(
    api: AsyncClient, token_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezo_api.account import entitlements

    monkeypatch.setitem(entitlements.LIMITS["free"], "document_jobs_per_day", 1)
    await api.get("/api/me", headers=OWNER)
    await make_owner_super_admin(token_app)
    _, secret = await new_user(api, "h@example.com")
    member = {"Authorization": f"Bearer {secret}"}
    first = await api.post("/api/student/readings", headers=member, json={"text": "Birinchi matn"})
    assert first.status_code == 201, first.text
    for path, kwargs in (
        ("/api/student/readings", {"json": {"text": "Ikkinchi matn"}}),
        ("/api/knowledge/urls", {"json": {"url": "https://example.com/a"}}),
        ("/api/knowledge/documents", {"files": {"file": ("a.txt", b"matn", "text/plain")}}),
    ):
        blocked = await api.post(path, headers=member, **kwargs)
        assert blocked.status_code == 429, (path, blocked.text)
        assert blocked.json()["error"]["code"] == "quota_exceeded"


async def test_jarvis_idempotent_retries_do_not_use_quota(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from ezo_api.account import entitlements
    from ezo_api.jarvis import service as jarvis_service
    from ezo_api.jarvis.telegram import TelegramClient
    from tests.integration.test_jarvis_tasks import (
        REFERENCE,
        Device,
        FakeTelegram,
        link_recipient,
        pair,
    )

    fake = FakeTelegram()
    client = TelegramClient("42:test-token", transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(jarvis_service.JarvisService, "_telegram", lambda self: client)
    monkeypatch.setitem(entitlements.LIMITS["free"], "jarvis_tasks_per_day", 1)
    settings = make_settings(
        database_url,
        EZO_AUTH_MODE="token",
        EZO_API_TOKEN=OWNER_TOKEN,
        EZO_TELEGRAM_BOT_TOKEN="42:test-token",
    )
    app = create_app(settings, providers={"anthropic": FakeProvider("anthropic")})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as api:
            await api.get("/api/me", headers=OWNER)
            await make_owner_super_admin(app)
            _, secret = await new_user(api, "i@example.com")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://t",
            headers={"Authorization": f"Bearer {secret}"},
        ) as member:
            # A refused request (no paired device yet) does not count.
            refused = await member.post(
                "/api/jarvis/tasks", json={"text": REFERENCE, "idempotency_key": "early-no-device"}
            )
            assert refused.json()["error"]["code"] == "no_paired_device", refused.text
            await pair(member, Device())
            await link_recipient(member, fake)
            body = {"text": REFERENCE, "idempotency_key": "same-key"}
            first = await member.post("/api/jarvis/tasks", json=body)
            assert first.status_code == 201, first.text
            retry = await member.post("/api/jarvis/tasks", json=body)
            assert retry.status_code == 201 and retry.json()["id"] == first.json()["id"]
            other = await member.post(
                "/api/jarvis/tasks", json={"text": REFERENCE, "idempotency_key": "another-new-key"}
            )
            assert other.status_code == 429, other.text
            assert other.json()["error"]["code"] == "quota_exceeded"
    finally:
        await app.state.services.db.dispose()
