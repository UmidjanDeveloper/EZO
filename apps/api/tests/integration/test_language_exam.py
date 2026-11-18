"""EZO's speaking exam simulator in a language other than English (fake model, real DB)."""

from __future__ import annotations

import json
from typing import Any

from httpx import AsyncClient

from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

ANSWER = (
    "Я живу в Ташкенте вместе с семьёй. Каждый день я езжу на работу на метро, потому что "
    "это быстро и удобно. В свободное время я люблю читать книги и гулять в парке с друзьями, "
    "а по выходным мы часто готовим плов."
)


def russian_assessment() -> str:
    data: dict[str, Any] = {
        "fluency_coherence": {"band": 5.0, "evidence": "связно, но короткие ответы"},
        "lexical_resource": {"band": 5.5, "evidence": "бытовая лексика"},
        "grammatical_range_accuracy": {"band": 5.0, "evidence": "простые конструкции"},
        "pronunciation": {"band": None, "evidence": ""},
        "cefr_estimate": "B1",
        "strengths": ["Javoblar izchil"],
        "weaknesses": ["Murakkab gaplar kam"],
        "mistakes": [],
        "better_sentences": [],
        "vocabulary": [],
        "practice_target": "Сложноподчинённые предложения",
        "summary": "B1 daraja.",
    }
    return json.dumps(data, ensure_ascii=False)


def system_of(fake: FakeProvider) -> str:
    return fake.requests[-1].system or ""


async def test_russian_exam_runs_three_parts_and_gives_a_cefr_level(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Хорошо. Следующий вопрос."
    start = await stream_chat(client, message="Rus tilidan imtihon ol")
    meta = start[0][1]
    assert meta["agent"] == "language_coach"
    conversation_id = meta["conversation_id"]
    system = system_of(fake_anthropic)
    assert "Practised language: Russian" in system
    assert "EXAM SIMULATOR" in system and "Part 1 (interview)" in system
    assert "3 parts" in system

    async def answer() -> list[tuple[str, dict[str, Any]]]:
        return await stream_chat(client, message=ANSWER, conversation_id=conversation_id)

    parts = []
    for _ in range(5):
        events = await answer()
        assert events[0][1]["agent"] == "language_coach"
        system = system_of(fake_anthropic)
        names = {1: "Part 1 (interview)", 2: "Part 2 (description)", 3: "Part 3 (discussion)"}
        parts.append(next(p for p, name in names.items() if name in system))
    assert parts == [1, 2, 2, 3, 3]

    fake_anthropic.replies = [russian_assessment(), "Natijangiz tayyor."]
    done = await answer()
    assess = fake_anthropic.requests[-2]
    assert "speaking practice / exam SIMULATOR in Russian" in (assess.system or "")
    assert "IELTS speaking criteria" not in (assess.system or "")
    system = system_of(fake_anthropic)
    assert "Russian — CEFR level estimate" in system and "Estimated level: B1" in system
    assert "Estimated band range" not in system

    [artifact] = done[-1][1]["message"]["metadata"]["artifacts"]
    [session] = (await client.get("/api/language/sessions")).json()
    assert (session["mode"], session["language"], session["status"]) == ("exam", "ru", "completed")
    assert session["cefr_estimate"] == "B1"
    assert session["band_low"] is None and session["band_high"] is None
    report = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/exports/markdown")
    text = report.text
    assert "Русский — og'zaki imtihon (simulyator)" in text
    assert "rasmiy imtihon yoki sertifikat emas" in text
    assert "IELTS" not in text


async def test_practice_in_german_and_switching_language(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Gern! Wie heißt du?"
    start = await stream_chat(client, message="Nemis tilida gaplashamiz")
    conversation_id = start[0][1]["conversation_id"]
    assert start[0][1]["agent"] == "language_coach"
    assert "Practised language: German" in system_of(fake_anthropic)
    # A learner's long answer that mentions another language does not switch the session.
    await stream_chat(
        client,
        message="Ich heiße Aziz und ich lerne Deutsch, aber ich spreche auch gut Englisch und "
        "ein bisschen Russisch mit meinen Freunden in Taschkent.",
        conversation_id=conversation_id,
    )
    assert "Practised language: German" in system_of(fake_anthropic)
    # A short command does.
    await stream_chat(
        client, message="Endi fransuz tilida gaplashamiz", conversation_id=conversation_id
    )
    assert "Practised language: French" in system_of(fake_anthropic)
    sessions = (await client.get("/api/language/sessions")).json()
    assert {s["language"] for s in sessions} == {"de", "fr"}
