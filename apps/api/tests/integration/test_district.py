"""District center end to end: a project, an Excel/CSV table and the official API as
sources, status in chat, warning drafts, and sending only after an explicit approval."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from ezo_api.db.models import AuditLog, DistrictNotice
from ezo_api.district.sms import EskizClient
from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.learning_web import FakeWeb

API = "https://bandlik.example.uz/api/xatlov"

TABLE = (
    b"F.I.Sh;Telefon;Mahalla;Reja;Bajarildi\n"
    b"Aliyev Botir;+998 90 111 22 33;Navbahor;100;5\n"
    b"Karimova Dilnoza;90 222 33 44;Guliston;100;70\n"
    b"Jami;;;200;75\n"
)


class FakeSms:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> Any:
        self.sent.append((phone, text))

        class Receipt:
            message_id = "eskiz-42"
            status = "waiting"

        return Receipt()


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def district_app(database_url: str, providers: dict[str, ModelProvider], web: FakeWeb) -> FastAPI:
    settings = make_settings(
        database_url,
        EZO_ESKIZ_EMAIL="owner@example.uz",
        EZO_ESKIZ_PASSWORD="not-a-real-password",
        EZO_DISTRICT_API_TOKEN="test-token-123",
    )
    return create_app(settings, providers=providers, fetcher=web.fetcher())


@pytest.fixture
async def api(district_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=district_app), base_url="http://test") as ac:
        yield ac
    await district_app.state.services.db.dispose()


async def make_project(api: AsyncClient, **extra: Any) -> dict[str, Any]:
    start = date.today() - timedelta(days=10)
    body = {
        "name": "Xatlov 2026",
        "unit": "xonadon",
        "responsible_org": "Xatirchi tumani bandlik bo'limi",
        "start_date": start.isoformat(),
        "deadline": (start + timedelta(days=20)).isoformat(),
        **extra,
    }
    response = await api.post("/api/district/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_table_import_status_chat_draft_and_approved_send(
    api: AsyncClient, district_app: FastAPI, fake_anthropic: FakeProvider
) -> None:
    project = await make_project(api)
    upload = await api.post(
        f"/api/district/projects/{project['id']}/import",
        files={"file": ("xatlov.csv", TABLE, "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json() == {"rows": 2, "created_people": 2, "updated": 2, "unchanged": 0}

    detail = (await api.get(f"/api/district/projects/{project['id']}")).json()
    status = detail["summary"]
    assert detail["project"]["status"] == "active"
    assert (status["target"], status["done"], status["percent"]) == (200, 75, 37.5)
    people = {p["name"]: p for p in detail["people"]}
    assert people["Aliyev Botir"]["behind"] is True  # 5 of ~50 expected by today
    assert people["Karimova Dilnoza"]["behind"] is False
    members = {m["full_name"]: m for m in (await api.get("/api/district/members")).json()}
    assert members["Aliyev Botir"]["phone"] == "998901112233"
    assert members["Karimova Dilnoza"]["phone"] == "998902223344"

    # Status in chat: the District Center answers from the stored numbers.
    fake_anthropic.reply = "Xatlov 37.5% da."
    events = await stream_chat(api, message="Xatlov qalay ketyapti?")
    assert events[0][1]["agent"] == "district"
    system = fake_anthropic.requests[-1].system or ""
    assert "Project «Xatlov 2026»: done 75 of 200 xonadon (37.5%)." in system
    assert "BEHIND: Aliyev Botir (Navbahor): 5 of 100" in system
    assert "998901112233" not in system  # phone numbers never go to the model

    # A warning is only a draft until the owner sends it.
    fake_anthropic.reply = "Qoralama tayyor, tekshirib yuboring."
    events = await stream_chat(
        api,
        message="Nega Aliyev xatlov qilmayapti, uni ogohlantir",
        conversation_id=events[0][1]["conversation_id"],
    )
    message = events[-1][1]["message"]
    [card] = message["metadata"]["district_notices"]
    assert card["status"] == "draft" and card["recipient_name"] == "Aliyev Botir"
    assert card["channels"] == ["sms"]
    assert "rejangiz 100 xonadon, bajarilgani 5 (5%)" in card["text"]
    assert card["text"].endswith("— Tuman hokimligi")
    assert "NOT sent" in (fake_anthropic.requests[-1].system or "")

    fake_sms = FakeSms()
    district_app.state.services.district_sms = fake_sms
    edited = card["text"].replace("bugun", "ertaga soat 10:00 gacha")
    sent = await api.post(f"/api/district/notices/{card['id']}/send", json={"text": edited})
    assert sent.status_code == 200, sent.text
    result = sent.json()
    assert result["status"] == "sent" and result["results"]["sms"]["id"] == "eskiz-42"
    assert fake_sms.sent == [("998901112233", edited)]
    again = await api.post(f"/api/district/notices/{card['id']}/send", json={})
    assert again.status_code == 409  # never sent twice

    async with district_app.state.services.db.sessionmaker() as session:
        actions = list(await session.scalars(select(AuditLog.action)))
        assert "district.notice_send" in actions and "district.import" in actions


async def test_official_api_source_is_read_with_the_server_token(
    api: AsyncClient, web: FakeWeb, fake_anthropic: FakeProvider
) -> None:
    web.add(
        API,
        {
            "data": {
                "items": [
                    {"inspector": {"fio": "Aliyev Botir", "id": "A-1"}, "plan": 100, "fact": 40},
                    {"inspector": {"fio": "Sodiqov Jasur", "id": "A-2"}, "plan": 80, "fact": 0},
                ]
            }
        },
    )
    source = {
        "url": API,
        "token_env": "EZO_DISTRICT_API_TOKEN",
        "items_path": "data.items",
        "fields": {"name": "inspector.fio", "external_id": "inspector.id", "target": "plan",
                   "done": "fact"},
    }  # fmt: skip
    project = await make_project(api, source_kind="api", source=source)
    assert "test-token-123" not in str(project)  # only the variable NAME is stored
    synced = await api.post(f"/api/district/projects/{project['id']}/sync")
    assert synced.json() == {"ok": True, "error": None, "updated": 2, "created_people": 2}
    assert web.headers[-1]["authorization"] == "Bearer test-token-123"

    fake_anthropic.reply = "Sodiqov hali boshlamagan."
    await stream_chat(api, message="Xatlov qalay ketyapti?")
    system = fake_anthropic.requests[-1].system or ""
    assert "done 40 of 180" in system and "BEHIND: Sodiqov Jasur: 0 of 80" in system
    assert "Source of the numbers: the official API" in system

    # A token variable outside the EZO_DISTRICT_API_TOKEN* family is refused.
    bad = await api.post(
        "/api/district/projects",
        json={"name": "Boshqa", "source_kind": "api",
              "source": {**source, "token_env": "ANTHROPIC_API_KEY"}},
    )  # fmt: skip
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_source"


async def test_behind_people_get_drafts_and_nothing_is_sent_without_a_channel(
    api: AsyncClient, district_app: FastAPI, fake_anthropic: FakeProvider
) -> None:
    project = await make_project(api)
    await api.post(
        f"/api/district/projects/{project['id']}/import",
        files={"file": ("x.csv", TABLE.replace(b"+998 90 111 22 33", b""), "text/csv")},
    )
    fake_anthropic.reply = "Qoralamalar tayyor."
    events = await stream_chat(api, message="Xatlov bo'yicha orqada qolganlarni ogohlantir")
    cards = events[-1][1]["message"]["metadata"]["district_notices"]
    assert [c["recipient_name"] for c in cards] == ["Aliyev Botir"]
    assert cards[0]["channels"] == []  # no phone, no Telegram
    refused = await api.post(f"/api/district/notices/{cards[0]['id']}/send", json={})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "no_channel"
    async with district_app.state.services.db.sessionmaker() as session:
        notice = await session.get(DistrictNotice, __import__("uuid").UUID(cards[0]["id"]))
        assert notice is not None and notice.status == "draft"


async def test_eskiz_client_logs_in_once_and_confirms_the_message() -> None:
    calls: list[tuple[str, dict[str, str], str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        calls.append((request.url.path, form, request.headers.get("authorization", "")))
        if request.url.path == "/api/auth/login":
            return httpx.Response(
                200, json={"message": "token_generated", "data": {"token": "T0K"}}
            )
        return httpx.Response(
            200, json={"id": "abc-1", "message": "Waiting for SMS provider", "status": "waiting"}
        )

    client = EskizClient("o@example.uz", "pw", "4546", transport=httpx.MockTransport(handler))
    first = await client.send("998901112233", "Salom")
    second = await client.send("998901112233", "Yana")
    assert (first.message_id, second.message_id) == ("abc-1", "abc-1")
    assert [c[0] for c in calls] == [
        "/api/auth/login",
        "/api/message/sms/send",
        "/api/message/sms/send",
    ]
    assert calls[1][1] == {"mobile_phone": "998901112233", "message": "Salom", "from": "4546"}
    assert calls[1][2] == "Bearer T0K"
