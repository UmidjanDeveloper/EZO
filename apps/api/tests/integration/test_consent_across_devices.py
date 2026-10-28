"""Memory consent is one server-side decision per account (section 11).

The same account on two devices = two tokens. Consent granted on the phone applies to the
laptop at once; consent revoked on the laptop stops capture on the phone's very next turn,
and the recall switch is shared the same way. Nothing is cached per device.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from ezo_api.db.models import User
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

OWNER_TOKEN = "owner-installation-token-0123456789abcdef"
OWNER = {"Authorization": f"Bearer {OWNER_TOKEN}"}


@pytest.fixture
async def token_app(database_url: str) -> AsyncIterator[FastAPI]:
    settings = make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN=OWNER_TOKEN)
    app = create_app(settings, providers={"anthropic": FakeProvider("anthropic")})
    yield app
    await app.state.services.db.dispose()


async def _devices(app: FastAPI) -> tuple[AsyncClient, AsyncClient]:
    """Two clients for ONE ordinary account: a phone token and a laptop token."""
    transport = ASGITransport(app=app)
    admin = AsyncClient(transport=transport, base_url="http://t", headers=OWNER)
    await admin.get("/api/me")
    async with app.state.services.db.sessionmaker() as session, session.begin():
        owner = await session.scalar(select(User))
        assert owner is not None
        owner.role = "super_admin"
    created = await admin.post(
        "/api/admin/users", json={"email": "dilnoza@example.com", "display_name": "Dilnoza"}
    )
    assert created.status_code == 201, created.text
    tokens = []
    for label in ("phone", "laptop"):
        token = await admin.post(
            f"/api/admin/users/{created.json()['id']}/tokens", json={"label": label}
        )
        assert token.status_code == 201, token.text
        tokens.append(token.json()["token"])
    await admin.aclose()
    return tuple(  # type: ignore[return-value]
        AsyncClient(
            transport=transport, base_url="http://t", headers={"Authorization": f"Bearer {t}"}
        )
        for t in tokens
    )


async def test_consent_changed_on_one_device_governs_the_other_at_once(token_app: FastAPI) -> None:
    phone, laptop = await _devices(token_app)
    try:
        assert (await laptop.get("/api/personal/profile")).json()["memory_consent"] is False

        # Phone grants consent → the laptop's next turn is captured.
        granted = await phone.post(
            "/api/personal/consent", json={"consent": True, "auto_memory": True}
        )
        assert granted.status_code == 200, granted.text
        assert (await laptop.get("/api/personal/profile")).json()["memory_consent"] is True
        await stream_chat(laptop, message="Eslab qol: men Toshkentda yashayman.")
        memories = (await laptop.get("/api/memories")).json()
        assert any("Toshkentda" in m["content"] for m in memories), memories
        assert (await phone.get("/api/memories")).json() == memories  # one account, one store

        # Laptop revokes consent → the phone's next turn stores nothing.
        revoked = await laptop.post(
            "/api/personal/consent", json={"consent": False, "auto_memory": False}
        )
        assert revoked.status_code == 200, revoked.text
        assert (await phone.get("/api/personal/profile")).json()["memory_consent"] is False
        before = len((await phone.get("/api/memories")).json())
        await stream_chat(phone, message="Eslab qol: mening sevimli rangim yashil.")
        after = (await phone.get("/api/memories")).json()
        assert len(after) == before, after
        assert not any("yashil" in m["content"] for m in after)

        # Recall off on the phone is recall off on the laptop (the profile is the single source).
        recall_off = await phone.post(
            "/api/personal/consent", json={"consent": False, "auto_memory": False, "recall": False}
        )
        assert recall_off.status_code == 200, recall_off.text
        assert (await laptop.get("/api/personal/profile")).json()["memory_recall"] is False
    finally:
        await phone.aclose()
        await laptop.aclose()
