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
    assert eval_data["fluency_score"] >= 4.0
    assert eval_data["lexical_score"] >= 4.0
    assert eval_data["grammar_score"] >= 4.0
    assert eval_data["estimated_band"] >= 4.0
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
