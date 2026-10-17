"""Language Coach end to end through the chat API (fake model, real database)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

ANSWER = (
    "Well, I live in Tashkent with my family and I goes to work by metro every day. "
    "I am working in a bank since two years, and honestly I enjoy it because my colleagues "
    "are friendly and the work is interesting for me."
)  # 44 words


def assessment(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "fluency_coherence": {"band": 6.0, "evidence": "speaks at length with linking words"},
        "lexical_resource": {"band": 6.0, "evidence": "adequate everyday vocabulary"},
        "grammatical_range_accuracy": {"band": 5.5, "evidence": "repeated tense errors"},
        "pronunciation": {"band": 7.0, "evidence": "transcript is clear"},
        "cefr_estimate": "B1",
        "strengths": ["Answers are well developed"],
        "weaknesses": ["Present perfect with for/since"],
        "mistakes": [
            {
                "category": "verb_tense",
                "original": "I am working in a bank since two years",
                "correction": "I have been working in a bank for two years",
                "explanation": "Use the present perfect continuous with for.",
                "severity": "minor",
            },
            {
                "category": "subject_verb_agreement",
                "original": "I goes to work",
                "correction": "I go to work",
                "explanation": "I + base verb.",
                "severity": "minor",
            },
            {
                "category": "articles",
                "original": "I bought the car yesterday",  # never said
                "correction": "I bought a car yesterday",
                "explanation": "invented",
            },
        ],
        "better_sentences": [
            {
                "original": "the work is interesting for me",
                "improved": "I find the work genuinely engaging",
            }
        ],
        "vocabulary": [
            {"term": "commute", "meaning": "travel to work", "example": "I commute by metro."}
        ],
        "practice_target": "Present perfect with for and since",
        "summary": "A solid B1-level performance.",
    }
    data.update(overrides)
    return json.dumps(data)


def last_system(fake: FakeProvider) -> str:
    return fake.requests[-1].system or ""


async def test_ielts_simulator_runs_three_parts_and_assesses(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Thank you. Let's continue."
    start = await stream_chat(client, message="IELTS speaking qilamiz, B2 darajada")
    meta = start[0][1]
    conversation_id = meta["conversation_id"]
    assert meta["agent"] == "language_coach" and meta["requested_agent_available"] is True
    system = last_system(fake_anthropic)
    assert "IELTS-style test, Part 1" in system and "not an official test" in system
    assert "Learner level B2" in system
    assert fake_anthropic.requests[-1].model == "claude-haiku-5-5"  # practice: cheap chat route

    async def answer(text: str = ANSWER, **body: Any) -> list[tuple[str, dict[str, Any]]]:
        events = await stream_chat(client, message=text, conversation_id=conversation_id, **body)
        assert (
            events[0][1]["agent"] == "language_coach"
        )  # an ordinary sentence stays with the coach
        return events

    for _ in range(5):  # Part 1
        await answer(channel="voice", speech_seconds=20.0)
    system = last_system(fake_anthropic)
    assert "Part 2" in system and "You should say:" in system and "one minute" in system
    await answer(" ".join([ANSWER] * 3), channel="voice", speech_seconds=60.0)  # long turn
    assert "rounding-off question" in last_system(fake_anthropic)
    await answer(channel="voice", speech_seconds=15.0)
    assert "Part 3" in last_system(fake_anthropic)
    for _ in range(3):
        await answer(channel="voice", speech_seconds=18.0)

    fake_anthropic.replies = [assessment(), "Ajoyib! Natijangiz tayyor."]
    done = await answer(channel="voice", speech_seconds=20.0)
    assess_request = fake_anthropic.requests[-2]
    assert assess_request.model == "claude-opus-5-5"  # the assessment: reasoning route
    assert "Transcript:" in assess_request.messages[0].content
    assert "Learner (Part 2, spoken, 60 s)" in assess_request.messages[0].content
    assert "Coach (Part 1)" in assess_request.messages[0].content  # EZO's questions recorded
    system = last_system(fake_anthropic)
    # mean of 6, 6 and 5.5 = 5.83 → the range covers its half-band rounding
    assert "Estimated band range (simulator, not official): 5.5–6." in system
    assert "transcript-assisted estimate 7" in system
    assert "“I goes to work” → “I go to work”" in system

    [artifact] = done[-1][1]["message"]["metadata"]["artifacts"]
    assert artifact["type"] == "report"

    sessions = (await client.get("/api/language/sessions")).json()
    assert len(sessions) == 1
    session = sessions[0]
    assert session["mode"] == "ielts" and session["status"] == "completed"
    assert (session["band_low"], session["band_high"]) == (5.5, 6.0)
    assert session["pronunciation_confidence"] == "transcript_assisted"
    assert session["cefr_target"] == "B2" and session["cefr_estimate"] == "B1"
    assert session["report_artifact_id"] == artifact["id"]
    assert session["speaking_seconds"] == 5 * 20 + 60 + 15 + 3 * 18 + 20

    detail = (await client.get(f"/api/language/sessions/{session['id']}")).json()
    learner_turns = [t for t in detail["turns"] if t["role"] == "learner"]
    assert len(learner_turns) == 11
    assert [t["ielts_part"] for t in learner_turns] == [1] * 5 + [2, 2] + [3] * 4
    assert {m["category"] for m in detail["mistakes"]} == {"verb_tense", "subject_verb_agreement"}
    metrics = {m["name"]: m for m in detail["metrics"]}
    assert metrics["words_per_minute"]["method"] == "computed"  # every turn was timed
    assert metrics["grammatical_range_accuracy"]["method"] == "estimated"

    report = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/exports/markdown")
    assert "not an official" in report.text or "rasmiy IELTS balli emas" in report.text
    vocabulary = (await client.get("/api/language/vocabulary")).json()
    assert vocabulary[0]["term"] == "commute"


async def test_free_practice_finish_progress_and_recurring_mistakes(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "That sounds great! What else?"
    start = await stream_chat(client, message="English speaking qilamiz")
    conversation_id = start[0][1]["conversation_id"]
    assert "free conversation practice session started" in last_system(fake_anthropic)
    for _ in range(2):
        await stream_chat(client, message=ANSWER, conversation_id=conversation_id)
    fake_anthropic.replies = [
        assessment(pronunciation={"band": 8, "evidence": "?"}),
        "Mana natija.",
    ]
    await stream_chat(client, message="Feedback ber", conversation_id=conversation_id)
    system = last_system(fake_anthropic)
    assert "Pronunciation: not assessed" in system  # typed session
    assert "Pronunciation was not assessed: the session was mostly typed." in system

    # A typed message is no longer routed to the coach once the session is finished.
    after = await stream_chat(
        client, message="Rahmat, bugun ob-havo qanday?", conversation_id=conversation_id
    )
    assert after[0][1]["agent"] == "general"

    # Progress questions use stored facts only.
    await stream_chat(client, message="Grammarim yaxshilandimi?")
    system = last_system(fake_anthropic)
    assert "Facts from the learner's last 1 completed sessions" in system
    assert "Only a few sessions exist" in system
    assert "verb tense ×1" in system

    # The next session quietly targets the recurring weak points.
    await stream_chat(client, message="Job interview practice please")
    system = last_system(fake_anthropic)
    assert "Act as a professional job interviewer" in system
    assert "often struggles with:" in system
    assert "verb tense" in system and "subject verb agreement" in system
    assert "Do NOT mention these weak points now" in system


async def test_goals_progress_api_and_privacy(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await stream_chat(client, message="Maqsadim IELTS 7.5 olish")
    assert "Saved the learner's goal" in last_system(fake_anthropic)
    progress = (await client.get("/api/language/progress")).json()
    assert progress["goals"][0]["target_band"] == 7.5 and progress["sessions"] == []
    created = await client.post(
        "/api/language/goals", json={"description": "Speak B2", "cefr_target": "B2"}
    )
    assert created.status_code == 201
    goals = (await client.get("/api/language/progress")).json()["goals"]
    assert [g["cefr_target"] for g in goals] == ["B2"]  # the new goal replaces the old one
    bad = await client.post("/api/language/goals", json={"description": "x", "cefr_target": "Z9"})
    assert bad.status_code == 422

    start = await stream_chat(client, message="English speaking qilamiz")
    sessions = (await client.get("/api/language/sessions")).json()
    session_id = sessions[0]["id"]
    assert sessions[0]["status"] == "active" and sessions[0]["cefr_target"] == "B2"
    assert (await client.delete(f"/api/language/sessions/{session_id}")).status_code == 409
    deleted = await client.delete(
        f"/api/language/sessions/{session_id}", params={"confirm": "true"}
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/api/language/sessions/{session_id}")).status_code == 404
    # Without an active session an English sentence is ordinary chat again.
    follow = await stream_chat(
        client, message="I live in Tashkent.", conversation_id=start[0][1]["conversation_id"]
    )
    assert follow[0][1]["agent"] == "general"


async def test_too_little_speech_gets_no_band(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    start = await stream_chat(client, message="English speaking qilamiz")
    conversation_id = start[0][1]["conversation_id"]
    await stream_chat(client, message="I like tea.", conversation_id=conversation_id)
    fake_anthropic.replies = [assessment(), "Natija."]
    await stream_chat(client, message="Tugatdim, baholang", conversation_id=conversation_id)
    system = last_system(fake_anthropic)
    assert "No band estimate was given." in system
    assert "at least 40 are needed" in system


async def test_offline_mode_is_honest(database_url: str) -> None:
    app: FastAPI = create_app(make_settings(database_url), providers={})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            events = await stream_chat(client, message="IELTS speaking qilamiz")
            assert events[0][1]["agent"] == "language_coach"
            assert (await client.get("/api/language/sessions")).json() == []
    finally:
        await app.state.services.db.dispose()
