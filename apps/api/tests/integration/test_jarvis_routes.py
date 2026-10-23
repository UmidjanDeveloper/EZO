"""Integration tests for /api/jarvis endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_jarvis_api_full_scenario_route(client: AsyncClient) -> None:
    # 1. Setup reference scenario fixtures
    setup_res = await client.post("/api/jarvis/companion/setup-scenario")
    assert setup_res.status_code == 200
    assert setup_res.json()["status"] == "ready"

    # 2. Check companion status
    status_res = await client.get("/api/jarvis/companion/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["pairing_status"] == "paired"
    assert "Downloads" in status_data["authorized_directories"]

    # 3. List companion files
    files_res = await client.get("/api/jarvis/companion/files?directory=Downloads")
    assert files_res.status_code == 200
    files_list = files_res.json()
    assert len(files_list) >= 2

    # 4. Create plan for reference prompt
    prompt = (
        "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, "
        "foiz ko'rsatkichlarini oldingi fayldagidek tayyorla va Telegram orqali Baxtiyorga yubor."
    )
    plan_res = await client.post("/api/jarvis/plan", json={"instruction": prompt, "language": "uz"})
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    plan_id = plan_data["id"]
    assert len(plan_data["steps"]) == 8

    # 5. Execute plan (should pause at step 6 awaiting approval)
    exec_res = await client.post(f"/api/jarvis/tasks/{plan_id}/execute")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "awaiting_approval"

    # Verify step 6 is awaiting approval
    approval_step = next(s for s in exec_data["steps"] if s["type"] == "security.request_approval")
    assert approval_step["status"] == "awaiting_approval"

    # 6. Submit user approval
    auth_res = await client.post(
        f"/api/jarvis/tasks/{plan_id}/authorize",
        json={"approved": True, "comment": "Tasdiqlandi"},
    )
    assert auth_res.status_code == 200
    completed_data = auth_res.json()
    assert completed_data["status"] == "completed"

    # 7. Check voice report step result
    voice_step = next(s for s in completed_data["steps"] if s["type"] == "voice.report_completion")
    assert voice_step["status"] == "completed"
    assert "Topshiriq muvaffaqiyatli bajarildi" in voice_step["result"]["voice_script_uz"]
