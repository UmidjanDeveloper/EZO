"""Jadval: recurring jobs from chat, timing, leases, runs, delivery to the owner's own chat."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from ezo_api.db.base import utcnow
from ezo_api.db.models import ScheduledJob, ScheduledRun, TelegramRecipient, User
from ezo_api.jarvis.telegram import TelegramClient
from ezo_api.schedule import service as schedule
from ezo_api.schedule.requests import parse, wants_schedule
from ezo_api.schedule.timing import describe, next_run
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

TZ = "Asia/Tashkent"


def test_next_run_weekly_daily_monthly() -> None:
    # Wednesday 2026-11-18 10:00 Tashkent (05:00 UTC).
    after = datetime(2026, 11, 18, 5, 0, tzinfo=UTC)
    monday = next_run(weekdays="1", at_time="09:00", month_day=None, timezone=TZ, after=after)
    assert monday == datetime(2026, 11, 23, 4, 0, tzinfo=UTC)
    daily = next_run(weekdays="", at_time="08:30", month_day=None, timezone=TZ, after=after)
    assert daily == datetime(2026, 11, 19, 3, 30, tzinfo=UTC)
    later_today = next_run(weekdays="", at_time="18:00", month_day=None, timezone=TZ, after=after)
    assert later_today == datetime(2026, 11, 18, 13, 0, tzinfo=UTC)
    month = next_run(weekdays="", at_time="09:00", month_day=31, timezone=TZ, after=after)
    assert month == datetime(2026, 11, 30, 4, 0, tzinfo=UTC)  # November has 30 days
    assert describe("1", "09:00", None) == "har dushanba 09:00"
    assert describe("1,2,3,4,5", "18:00", None) == "ish kunlari 18:00"
    assert describe("", "09:00", 1) == "har oyning 1-kuni 09:00"


def test_requests_are_read_without_a_model() -> None:
    weekly = parse("Har dushanba soat 9 da haftalik hisobot tayyorla")
    assert (weekly.kind, weekly.weekdays, weekly.at_time) == ("weekly_report", "1", "09:00")
    digest = parse("Har kuni ertalab 8:30 da muddatlarni eslat")
    assert (digest.kind, digest.weekdays, digest.at_time) == ("deadline_digest", "", "08:30")
    monthly = parse("Har oyning 1-kuni oylik hisobot tayyorlab telegramga yubor")
    assert (monthly.kind, monthly.month_day, monthly.telegram) == ("monthly_report", 1, True)
    evening = parse("Ish kunlari kechqurun 6 da xatlov loyihalarini yangila")
    assert (evening.kind, evening.weekdays, evening.at_time) == (
        "district_sync",
        "1,2,3,4,5",
        "18:00",
    )
    sunday = parse("Har yakshanba lex.uz qonunlarni qayta tekshir")
    assert (sunday.kind, sunday.weekdays) == ("lexuz_recheck", "7")
    assert parse("Каждый понедельник в 10 отчёт").at_time == "10:00"
    assert wants_schedule("Har dushanba haftalik hisobot")
    assert not wants_schedule("Haftalik hisobot tayyorla")  # a one-off report stays Devonxona
    assert wants_schedule("Jadvalimni ko'rsat")


async def _owner(app: FastAPI, client: AsyncClient) -> uuid.UUID:
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        assert user is not None
        return user.id


async def test_chat_schedules_lists_and_stops(
    app: FastAPI, client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Rejalashtirildi."
    events = await stream_chat(client, message="Har dushanba soat 9 da haftalik hisobot tayyorla")
    assert events[0][1]["agent"] == "schedule"
    system = fake_anthropic.requests[-1].system or ""
    assert "EZO scheduled «Haftalik hisobot» — har dushanba 09:00" in system
    [job] = (await client.get("/api/schedule")).json()["jobs"]
    assert job["kind"] == "weekly_report" and job["enabled"] is True
    # Saying it again does not make a second job.
    await stream_chat(client, message="Har dushanba soat 9 da haftalik hisobot tayyorla")
    assert len((await client.get("/api/schedule")).json()["jobs"]) == 1

    await stream_chat(client, message="Jadvalimni ko'rsat")
    assert "«Haftalik hisobot» — har dushanba 09:00, next" in (
        fake_anthropic.requests[-1].system or ""
    )

    await stream_chat(client, message="Haftalik hisobot jadvalini to'xtat")
    assert "EZO stopped: «Haftalik hisobot»" in (fake_anthropic.requests[-1].system or "")
    [job] = (await client.get("/api/schedule")).json()["jobs"]
    assert job["enabled"] is False


async def test_due_jobs_run_once_with_a_lease_and_move_on(
    app: FastAPI, client: AsyncClient
) -> None:
    user_id = await _owner(app, client)
    services = app.state.services
    async with services.db.sessionmaker() as session:
        job = await schedule.create_job(
            session, user_id, kind="deadline_digest", timezone=TZ, at_time="08:00"
        )
        job.next_run_at = utcnow() - timedelta(days=3)  # EZO was off for three days
        await session.commit()
        job_id = job.id
    # A second runner holding a live lease blocks this one.
    async with services.db.sessionmaker() as session:
        assert await schedule.claim_due(session, utcnow()) == [job_id]
    async with services.db.sessionmaker() as session:
        assert await schedule.claim_due(session, utcnow()) == []
    await schedule.run_job(services, job_id)
    async with services.db.sessionmaker() as session:
        job = await session.get(ScheduledJob, job_id)
        assert job is not None and job.locked_until is None and job.last_status == "completed"
        assert job.next_run_at > utcnow()  # missed days ran once, not three times
        runs = list(await session.scalars(select(ScheduledRun)))
    assert len(runs) == 1 and "muddati o‘tgan yoki 3 kun ichida" in runs[0].summary
    assert await schedule.tick(services) == 0


async def test_weekly_report_makes_a_word_file_and_goes_to_own_telegram(
    app: FastAPI, client: AsyncClient
) -> None:
    user_id = await _owner(app, client)
    await client.post(
        "/api/chancery/appeals",
        json={"applicant": "Karimov Aziz", "summary": "Ko'cha chirog'i yonmayapti."},
    )
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append({"path": request.url.path, "body": request.content.decode()})
        return httpx.Response(200, json={"ok": True, "result": {
            "message_id": 7, "date": int(time.time()), "chat": {"id": 555, "type": "private"},
        }})  # fmt: skip

    services = app.state.services
    services.settings.telegram_bot_token = SecretStr("123:test")
    services.district_telegram = TelegramClient("123:test", transport=httpx.MockTransport(handler))
    async with services.db.sessionmaker() as session:
        own = TelegramRecipient(user_id=user_id, label="Men", status="verified", chat_id="555")
        session.add(own)
        await session.flush()
        job = await schedule.create_job(
            session, user_id, kind="weekly_report", timezone=TZ, weekdays="1",
            notify_recipient_id=own.id,
        )  # fmt: skip
        await session.commit()
        job_id = job.id
    response = await client.post(f"/api/schedule/{job_id}/run")
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed" and run["artifact_id"] and run["notified"] is True
    assert "Haftalik hisobot" in run["summary"]
    assert sent and sent[0]["path"].endswith("/sendMessage") and "555" in sent[0]["body"]
    download = await client.get(f"/api/artifacts/{run['artifact_id']}/versions/1/download")
    assert download.status_code == 200 and download.content[:2] == b"PK"


async def test_api_rejects_a_foreign_or_unlinked_chat(app: FastAPI, client: AsyncClient) -> None:
    await _owner(app, client)
    response = await client.post(
        "/api/schedule",
        json={"kind": "deadline_digest", "notify_recipient_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "recipient_not_linked"
    bad_time = await client.post(
        "/api/schedule", json={"kind": "deadline_digest", "at_time": "25:00"}
    )
    assert bad_time.status_code == 422
    ok = await client.post("/api/schedule", json={"kind": "district_sync", "weekdays": "1,3"})
    assert ok.status_code == 201 and ok.json()["when"] == "har dushanba, chorshanba 09:00"
    job_id = ok.json()["id"]
    off = await client.patch(f"/api/schedule/{job_id}", json={"enabled": False})
    assert off.json()["enabled"] is False
    assert (await client.delete(f"/api/schedule/{job_id}")).status_code == 204
