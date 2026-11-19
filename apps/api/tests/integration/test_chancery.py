"""Devonxona end to end: appeals, minutes with tasks, reminders and the report (fake model)."""

from __future__ import annotations

import io
import json
from datetime import date, timedelta

from docx import Document
from httpx import AsyncClient

from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


def today() -> date:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Tashkent")).date()


async def docx_text(client: AsyncClient, artifact_id: str) -> str:
    response = await client.get(f"/api/artifacts/{artifact_id}/versions/1/download")
    assert response.status_code == 200
    return "\n".join(p.text for p in Document(io.BytesIO(response.content)).paragraphs) + "\n".join(
        c.text
        for t in Document(io.BytesIO(response.content)).tables
        for r in t.rows
        for c in r.cells
    )


async def add_person(client: AsyncClient, name: str, phone: str) -> None:
    response = await client.post("/api/district/members", json={"full_name": name, "phone": phone})
    assert response.status_code == 201, response.text


async def test_appeal_register_reply_letter_and_answered(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await add_person(client, "Aliyev Botir", "+998901112233")
    extracted = {
        "applicant": "Karimov Aziz", "contact": "Navbahor MFY, 5-uy",
        "channel": "virtual_reception",
        "summary": "Ko'chadagi chiroqlar ikki haftadan beri yonmayapti.", "received_on": None,
        "due_on": None, "assignee": "Aliyev",
    }  # fmt: skip
    fake_anthropic.replies = [json.dumps(extracted), "Ro'yxatga olindi."]
    events = await stream_chat(
        client,
        message="Yangi murojaat: Karimov Aziz, Navbahor MFY, ko'cha chirog'i yonmayapti, "
        "virtual qabulxona orqali, Aliyevga topshirilsin",
    )
    assert events[0][1]["agent"] == "chancery"
    year = today().year
    system = fake_anthropic.requests[-1].system or ""
    assert f"Registered: M-{year}-0001 — Karimov Aziz (Virtual qabulxona" in system
    due = today() + timedelta(days=15)
    assert f"due {due.isoformat()} (15 day(s) left); handled by Aliyev Botir." in system

    [appeal] = (await client.get("/api/chancery/appeals")).json()
    assert appeal["number"] == f"M-{year}-0001" and appeal["assignee_known"] is True

    fake_anthropic.replies = [
        "Hurmatli Karimov Aziz!\n\nSizning murojaatingiz ko'rib chiqildi. "
        "Chiroqlar shu hafta ichida tiklanadi.",
        "Javob xati tayyor.",
    ]
    events = await stream_chat(
        client, message=f"M-{year}-0001 ga javob xati tayyorla: shu hafta tuzatiladi"
    )
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    text = await docx_text(client, artifact["id"])
    assert "Karimov Aziz" in text and "shu hafta ichida tiklanadi" in text

    fake_anthropic.reply = "Yopildi."
    await stream_chat(client, message=f"M-{year}-0001 ga javob berildi")
    [appeal] = (await client.get("/api/chancery/appeals")).json()
    assert appeal["status"] == "answered" and appeal["answer_artifact_id"] == artifact["id"]


async def test_minutes_make_tasks_reminders_and_report(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await add_person(client, "Aliyev Botir", "+998901112233")
    past = (today() - timedelta(days=2)).isoformat()
    minutes = {
        "title": "Obodonlashtirish bo'yicha yig'ilish", "held_on": None, "chair": "Hokim",
        "attendees": ["Aliyev B.", "Karimova D."], "agenda": ["Ko'cha chiroqlari"],
        "discussion": ["Chiroqlar ishlamayapti"], "decisions": ["Chiroqlar tiklansin"],
        "tasks": [
            {"title": "Navbahor MFY chiroqlarini tiklash", "assignee": "Aliyev", "due_on": past},
            {"title": "Hisobot tayyorlash", "assignee": "Sobirov", "due_on": None},
        ],
    }  # fmt: skip
    fake_anthropic.replies = [json.dumps(minutes), "Bayonnoma tayyor."]
    notes = (
        "Yig'ilish bayonnomasini tuz: bugun hokim raisligida obodonlashtirish yig'ilishi bo'ldi. "
        "Aliyev chiroqlarni tiklasin, Sobirov hisobot tayyorlasin."
    )
    events = await stream_chat(client, message=notes)
    assert events[0][1]["agent"] == "chancery"
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    text = await docx_text(client, artifact["id"])
    assert "Qaror qilindi" in text and "Navbahor MFY chiroqlarini tiklash" in text
    year = today().year
    tasks = {t["number"]: t for t in (await client.get("/api/chancery/tasks")).json()}
    assert tasks[f"T-{year}-0001"]["state"] == "overdue"
    assert tasks[f"T-{year}-0002"]["assignee_known"] is False
    system = fake_anthropic.requests[-1].system or ""
    assert "not among the district's known people" in system

    fake_anthropic.reply = "Eslatmalar tayyor."
    events = await stream_chat(client, message="Muddati o'tganlarni eslat")
    [card] = events[-1][1]["message"]["metadata"]["district_notices"]
    assert card["recipient_name"] == "Aliyev Botir" and card["status"] == "draft"
    assert f"T-{year}-0001 topshiriq" in card["text"]

    fake_anthropic.reply = "Bajarildi deb belgilandi."
    await stream_chat(client, message=f"T-{year}-0001 bajarildi")
    tasks = {t["number"]: t for t in (await client.get("/api/chancery/tasks")).json()}
    assert tasks[f"T-{year}-0001"]["status"] == "done"

    fake_anthropic.reply = "Hisobot tayyor."
    events = await stream_chat(client, message="Haftalik hisobot tayyorla")
    [report] = events[-1][1]["message"]["metadata"]["artifacts"]
    text = await docx_text(client, report["id"])
    assert "Berilgan: 2" in text and "Bajarilgan: 1" in text
    assert "tasks given: 2, tasks done: 1" in (fake_anthropic.requests[-1].system or "")


async def test_overview_is_honest_when_empty(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Hali hech narsa yo'q."
    await stream_chat(client, message="Topshiriqlar holati qanday?")
    assert "The devonxona register is empty" in (fake_anthropic.requests[-1].system or "")
