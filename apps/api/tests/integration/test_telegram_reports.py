"""Employees report progress to EZO's Telegram bot (fake Telegram, real database)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from ezo_api.db.models import (
    DistrictAssignment,
    DistrictMember,
    DistrictProject,
    TelegramInboxMessage,
    TelegramRecipient,
    User,
)
from ezo_api.district.telegram_reports import parse_report, poll_once
from ezo_api.jarvis.telegram import TelegramClient

CHAT = "5550001"


class FakeBot:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.sent: list[tuple[str, str]] = []
        self.offsets: list[int | None] = []

    def add(self, chat: str, text: str) -> None:
        update_id = 100 + len(self.updates)
        self.updates.append({
            "update_id": update_id,
            "message": {"message_id": update_id, "date": 1_800_000_000, "text": text,
                        "chat": {"id": int(chat), "type": "private"},
                        "from": {"first_name": "Botir"}},
        })  # fmt: skip

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        form = dict(httpx.QueryParams(request.content.decode()))
        if method == "getUpdates":
            offset = int(form["offset"]) if "offset" in form else None
            self.offsets.append(offset)
            result = [u for u in self.updates if offset is None or u["update_id"] >= offset]
            return httpx.Response(200, json={"ok": True, "result": result})
        if method == "sendMessage":
            self.sent.append((form["chat_id"], form["text"]))
            return httpx.Response(200, json={"ok": True, "result": {
                "message_id": len(self.sent), "chat": {"id": int(form["chat_id"])}}})  # fmt: skip
        return httpx.Response(404, json={"ok": False, "description": "unknown"})


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


async def setup_district(app: FastAPI, projects: list[tuple[str, float, float]]) -> uuid.UUID:
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User).limit(1))
        assert user is not None
        recipient = TelegramRecipient(
            user_id=user.id, label="Botir", status="verified", chat_id=CHAT
        )
        session.add(recipient)
        await session.flush()
        member = DistrictMember(
            user_id=user.id, full_name="Aliyev Botir", telegram_recipient_id=recipient.id
        )
        session.add(member)
        await session.flush()
        for name, target, done in projects:
            project = DistrictProject(user_id=user.id, name=name, unit="xonadon")
            session.add(project)
            await session.flush()
            session.add(
                DistrictAssignment(
                    project_id=project.id, member_id=member.id, target=target, done=done
                )
            )
        await session.commit()
        return member.id


async def poll(app: FastAPI, bot: FakeBot) -> None:
    client = TelegramClient("123:test", transport=httpx.MockTransport(bot.handler))
    async with app.state.services.db.sessionmaker() as session:
        await poll_once(session, client)
        await session.commit()


async def done_of(app: FastAPI, project: str) -> float:
    async with app.state.services.db.sessionmaker() as session:
        row = await session.scalar(
            select(DistrictAssignment).join(DistrictProject).where(DistrictProject.name == project)
        )
        assert row is not None
        return row.done


@pytest.mark.parametrize(
    ("text", "value", "absolute"),
    [("12", 12, False), ("bugun 12 ta", 12, False), ("jami 45", 45, True), ("=45", 45, True),
     ("xatlov 7", 7, False)],
)  # fmt: skip
def test_parse_report(text: str, value: float, absolute: bool) -> None:
    report = parse_report(text)
    assert report is not None and (report.value, report.absolute) == (value, absolute)
    assert parse_report("salom") is None and parse_report("12 va 14") is None


async def test_linked_person_reports_and_gets_a_reply(
    client: AsyncClient, app: FastAPI, bot: FakeBot
) -> None:
    await client.get("/api/me")  # creates the local owner
    await setup_district(app, [("Xatlov 2026", 100, 5)])
    bot.add(CHAT, "12")
    bot.add("999", "50")  # a stranger: stored, never answered
    bot.add(CHAT, "salom")
    await poll(app, bot)
    assert await done_of(app, "Xatlov 2026") == 17
    assert bot.sent[0] == (CHAT, "✅ Qabul qilindi: «Xatlov 2026» — 17 / 100 xonadon (17%).")
    assert bot.sent[1][0] == CHAT and "jami 45" in bot.sent[1][1]  # the help text
    assert all(chat != "999" for chat, _ in bot.sent)

    bot.add(CHAT, "jami 45")
    await poll(app, bot)
    assert await done_of(app, "Xatlov 2026") == 45
    assert bot.offsets[-1] == 103  # read once, confirmed: never re-read
    async with app.state.services.db.sessionmaker() as session:
        outcomes = [
            m.outcome
            for m in await session.scalars(
                select(TelegramInboxMessage).order_by(TelegramInboxMessage.update_id)
            )
        ]
    assert outcomes == ["applied", "unknown_sender", "help", "applied"]

    detail = (await client.get("/api/district/projects")).json()
    assert detail[0]["summary"]["done"] == 45


async def test_two_projects_need_the_project_name(
    client: AsyncClient, app: FastAPI, bot: FakeBot
) -> None:
    await client.get("/api/me")
    await setup_district(app, [("Xatlov 2026", 100, 0), ("Bandlik dasturi", 20, 0)])
    bot.add(CHAT, "5")
    await poll(app, bot)
    assert "Qaysi loyiha" in bot.sent[-1][1]
    bot.add(CHAT, "bandlik 3")
    await poll(app, bot)
    assert await done_of(app, "Bandlik dasturi") == 3 and await done_of(app, "Xatlov 2026") == 0


async def test_start_links_are_kept_for_recipient_verification(
    client: AsyncClient, app: FastAPI, bot: FakeBot
) -> None:
    from ezo_api.district.telegram_reports import find_start

    bot.add(CHAT, "/start abc123")
    await poll(app, bot)
    async with app.state.services.db.sessionmaker() as session:
        found = await find_start(session, "abc123")
    assert found is not None and found.chat_id == CHAT and found.sender_name == "Botir"
    assert bot.sent == []  # commands are never answered by the report handler
