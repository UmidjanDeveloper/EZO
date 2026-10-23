"""Integration tests for IELTS Examiner 2.0 workflow and Voice Adapter."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ielts_cue_cards_listing(client: AsyncClient) -> None:
    resp = await client.get("/api/ielts/cue-cards")
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) >= 3
    first = cards[0]
    assert "id" in first
    assert "task" in first
    assert len(first["points"]) >= 3
    assert "follow_up" in first
    assert len(first["discussion"]) >= 3


@pytest.mark.asyncio
async def test_ielts_voice_status_fallback(client: AsyncClient) -> None:
    resp = await client.get("/api/ielts/voice-status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["available"] is False
    assert status["fallback_mode"] == "text"
    assert "Ovozli xizmat" in status["notice_uz"]
    assert "Voice service" in status["notice_en"]
    assert "Rasmiy IELTS sertifikati emas" in status["notice_uz"]


@pytest.mark.asyncio
async def test_ielts_evaluate_direct_answer(client: AsyncClient) -> None:
    answer = (
        "In my free time, I really enjoy reading programming books and playing "
        "chess with my friends because it helps me develop strategic thinking."
    )
    resp = await client.post("/api/ielts/evaluate", json={"answer": answer, "part": 1})
    assert resp.status_code == 200
    eval_data = resp.json()
    assert eval_data["fluency_score"] is None
    assert eval_data["lexical_score"] is None
    assert eval_data["grammar_score"] is None
    assert eval_data["estimated_band"] is None
    assert "constructive_feedback" in eval_data
    assert "explanation_uz" in eval_data
    assert "rasmiy ielts sertifikati emas" in eval_data["disclaimer"].lower()


@pytest.mark.asyncio
async def test_ielts_full_session_lifecycle(client: AsyncClient) -> None:
    # 1. Start IELTS session
    create_resp = await client.post("/api/ielts/sessions", json={"target_band": 7.0})
    assert create_resp.status_code == 200
    session_data = create_resp.json()
    session_id = session_data["id"]
    assert session_data["status"] == "active"
    assert session_data["ielts_part"] == 1
    assert session_data["current_prompt"] is not None

    # 2. Get session details
    get_resp = await client.get(f"/api/ielts/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id

    # 3. Advance Part 1 answers
    adv1 = await client.post(
        f"/api/ielts/sessions/{session_id}/advance",
        json={
            "answer": "I am from Tashkent and it is known for historic architecture.",
            "speech_seconds": 15.0,
        },
    )
    assert adv1.status_code == 200
    assert adv1.json()["session_id"] == session_id
    assert not adv1.json()["finished"]

    # 4. Check history & stats
    hist_resp = await client.get("/api/ielts/history")
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert any(h["id"] == session_id for h in history)

    stats_resp = await client.get("/api/ielts/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_sessions"] >= 1


# --- computed practice metrics (PR #32) ------------------------------------------------

SHORT = "I live in a city near a river."  # 8 words
LONG_TURN = " ".join(["I learned to cook plov from my grandmother at home."] * 9)  # 90 words


async def _advance(client: AsyncClient, sid: str, answer: str, seconds: float | None) -> dict:
    payload: dict = {"answer": answer}
    if seconds is not None:
        payload["speech_seconds"] = seconds
    r = await client.post(f"/api/ielts/sessions/{sid}/advance", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_no_scores(body: dict) -> None:
    assert body["estimated_band_low"] is None
    assert body["estimated_band_high"] is None


@pytest.mark.asyncio
async def test_ielts_evaluate_returns_exact_metrics_without_band(client: AsyncClient) -> None:
    answer = "Um, I like tea. Um, I like tea. Um, I like tea because tea is nice."
    data = (await client.post("/api/ielts/evaluate", json={"answer": answer, "part": 2})).json()
    m = data["metrics"]
    assert m["words"] == 16 and m["fillers"] == 3
    assert m["part"] == 2 and m["answer_kind"] == "part2_long_turn"
    assert m["words_per_minute"] is None and m["reported_speech_seconds"] is None
    assert m["timing_source"] == "none" and m["audio_analyzed"] is False
    for key in ("fluency_score", "lexical_score", "grammar_score", "pronunciation_score"):
        assert data[key] is None
    assert data["estimated_band"] is None and data["estimated_band_low"] is None
    assert any("80+ words" in o for o in m["observations_en"])
    assert any("To'ldiruvchi" in o for o in m["observations_uz"])
    assert "not official IELTS band criteria" in m["heuristic_notice_en"]
    assert "rasmiy IELTS baholash mezonlari emas" in m["heuristic_notice_uz"]


@pytest.mark.asyncio
async def test_ielts_answer_metrics_use_the_part_answered_not_the_next(
    client: AsyncClient,
) -> None:
    sid = (await client.post("/api/ielts/sessions", json={})).json()["id"]
    for _ in range(4):
        body = await _advance(client, sid, SHORT, 3.0)
        assert body["part"] == 1 and body["metrics"]["part"] == 1

    # Part 1 -> Part 2: the 5th Part 1 answer moves the test on, but is judged as Part 1.
    body = await _advance(client, sid, SHORT, 3.0)
    assert body["part"] == 2
    assert body["metrics"]["part"] == 1 and body["metrics"]["answer_kind"] == "part1"
    assert any("15+ words" in o for o in body["metrics"]["observations_en"])

    # Part 2 long turn: judged against the long-turn heuristic.
    body = await _advance(client, sid, "I am proud of cooking.", 4.0)
    assert body["part"] == 2
    assert body["metrics"]["answer_kind"] == "part2_long_turn"
    assert any("80+ words" in o for o in body["metrics"]["observations_en"])

    # Part 2 -> Part 3: the short rounding-off answer is still a Part 2 follow-up.
    body = await _advance(client, sid, "Yes, I still cook it every week.", 3.0)
    assert body["part"] == 3
    m = body["metrics"]
    assert m["part"] == 2 and m["answer_kind"] == "part2_follow_up"
    assert not any("Short answer" in o for o in m["observations_en"])
    _assert_no_scores(body)

    body = await _advance(client, sid, SHORT, 3.0)
    assert body["metrics"]["part"] == 3 and body["metrics"]["answer_kind"] == "part3"


@pytest.mark.asyncio
async def test_ielts_session_metrics_separate_parts_from_overall(client: AsyncClient) -> None:
    sid = (await client.post("/api/ielts/sessions", json={})).json()["id"]
    plan = [SHORT] * 5 + [LONG_TURN, "Yes, I still cook it every week."] + [SHORT] * 4
    body: dict = {}
    for answer in plan:
        body = await _advance(client, sid, answer, 6.0)
        if body["finished"]:
            break
    assert body["finished"] is True
    _assert_no_scores(body)
    assert "No AI" in body["feedback"]

    sm = body["session_metrics"]
    overall = sm["overall"]
    assert "observations_en" not in overall  # numbers only
    assert overall["answers"] == 11
    assert overall["words"] == 5 * 8 + 90 + 7 + 4 * 8
    assert overall["timing_source"] == "client_reported"
    assert overall["reported_speech_seconds"] == 66.0
    assert overall["words_per_minute"] == round(overall["words"] / (66.0 / 60), 1)
    assert overall["audio_analyzed"] is False

    parts = {p["part"]: p for p in sm["per_part"]}
    assert {k: v["answers"] for k, v in parts.items()} == {1: 5, 2: 2, 3: 4}
    # Part 1 answers miss the Part 1 heuristic; Part 2's long turn and follow-up do not.
    assert any("5 of 5 answers" in o for o in parts[1]["observations_en"])
    assert not any("answers are shorter" in o for o in parts[2]["observations_en"])
    assert any("4 of 4 answers" in o for o in parts[3]["observations_en"])
    assert "not official IELTS band criteria" in sm["heuristic_notice_en"]

    session = (await client.get(f"/api/ielts/sessions/{sid}")).json()
    assert session["band_low"] is None and session["band_high"] is None


@pytest.mark.asyncio
async def test_ielts_pace_needs_reported_time_for_every_answer(client: AsyncClient) -> None:
    sid = (await client.post("/api/ielts/sessions", json={})).json()["id"]
    body: dict = {}
    for n in range(11):
        body = await _advance(client, sid, SHORT, None if n == 0 else 5.0)
    assert body["finished"] is True
    sm = body["session_metrics"]
    assert sm["overall"]["words_per_minute"] is None
    assert sm["overall"]["timing_source"] == "none"
    parts = {p["part"]: p for p in sm["per_part"]}
    assert parts[1]["words_per_minute"] is None  # one Part 1 answer had no time
    assert parts[3]["timing_source"] == "client_reported"
    assert body["metrics"]["timing_source"] == "client_reported"
    assert all("audio not analysed" in o for o in parts[3]["observations_en"] if "wpm" in o)
