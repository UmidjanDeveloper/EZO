"""Owner invites an employee: one-time link → own password → own, separate account."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.auth.passwords import PasswordError, check_strength, hash_password, verify_password
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.test_accounts import OWNER, OWNER_TOKEN, make_owner_super_admin

# Throwaway passwords for these tests only.
GOOD = "-".join(("Toshkent", "2026"))
OTHER = "-".join(("Other", "pass", "9"))
WRONG = "-".join(("nope", "nope"))


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


def test_passwords_are_hashed_and_checked() -> None:
    stored = hash_password(GOOD)
    assert stored.startswith("scrypt$") and GOOD not in stored
    assert verify_password(GOOD, stored)
    assert not verify_password(GOOD.lower(), stored)
    assert not verify_password("anything", None)
    for weak in ("short", "12345678", "aaaaaaaa"):
        with pytest.raises(PasswordError):
            check_strength(weak)


async def _invite(api: AsyncClient, app: FastAPI, email: str) -> tuple[str, str]:
    await api.get("/api/personal/profile", headers=OWNER)
    await make_owner_super_admin(app)
    created = await api.post(
        "/api/admin/users", headers=OWNER, json={"email": email, "display_name": "Aliyev Botir"}
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    invite = await api.post(f"/api/admin/users/{user_id}/invite", headers=OWNER)
    assert invite.status_code == 201, invite.text
    body = invite.json()
    assert body["path"] == f"/join#code={body['code']}"
    return user_id, body["code"]


async def test_invite_set_password_login_and_logout(api: AsyncClient, token_app: FastAPI) -> None:
    _, code = await _invite(api, token_app, "botir@hokimiyat.uz")
    info = await api.post("/api/auth/invite", json={"code": code})
    assert info.status_code == 200 and info.json()["email"] == "botir@hokimiyat.uz"

    weak = await api.post("/api/auth/accept-invite", json={"code": code, "password": "123"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    accepted = await api.post("/api/auth/accept-invite", json={"code": code, "password": GOOD})
    assert accepted.status_code == 200, accepted.text
    token = accepted.json()["token"]
    me = await api.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "botir@hokimiyat.uz"

    # The link works only once.
    again = await api.post("/api/auth/accept-invite", json={"code": code, "password": OTHER})
    assert again.status_code == 404 and again.json()["error"]["code"] == "invite_invalid"

    wrong = await api.post(
        "/api/auth/login", json={"email": "botir@hokimiyat.uz", "password": WRONG}
    )
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "login_failed"
    nobody = await api.post("/api/auth/login", json={"email": "x@y.uz", "password": GOOD})
    assert nobody.status_code == 401 and nobody.json()["error"]["code"] == "login_failed"
    login = await api.post(
        "/api/auth/login", json={"email": "Botir@Hokimiyat.uz", "password": GOOD}
    )
    assert login.status_code == 200
    second = {"Authorization": f"Bearer {login.json()['token']}"}

    # The employee is a normal user: not the owner, cannot manage accounts.
    assert (await api.get("/api/admin/users", headers=second)).status_code == 403

    assert (await api.post("/api/auth/logout", headers=second)).status_code == 204
    assert (await api.get("/api/me", headers=second)).status_code == 401


async def test_a_new_invite_cancels_the_old_one_and_attempts_are_limited(
    api: AsyncClient, token_app: FastAPI
) -> None:
    user_id, first = await _invite(api, token_app, "nodira@hokimiyat.uz")
    second = (await api.post(f"/api/admin/users/{user_id}/invite", headers=OWNER)).json()["code"]
    assert (await api.post("/api/auth/invite", json={"code": first})).status_code == 404
    assert (await api.post("/api/auth/invite", json={"code": second})).status_code == 200
    statuses = [
        (
            await api.post(
                "/api/auth/login", json={"email": "nodira@hokimiyat.uz", "password": f"guess-{i}xx"}
            )
        ).status_code
        for i in range(12)
    ]
    assert 429 in statuses


async def test_local_mode_refuses_invites(client: AsyncClient, app: FastAPI) -> None:
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session, session.begin():
        from sqlalchemy import select

        from ezo_api.db.models import User

        owner = await session.scalar(select(User))
        assert owner is not None
        owner.role = "super_admin"
    created = await client.post("/api/admin/users", json={"email": "a@b.uz", "display_name": "A"})
    response = await client.post(f"/api/admin/users/{created.json()['id']}/invite")
    assert response.status_code == 409 and response.json()["error"]["code"] == "local_mode"
    login = await client.post("/api/auth/login", json={"email": "a@b.uz", "password": WRONG + "1"})
    assert login.status_code == 409
