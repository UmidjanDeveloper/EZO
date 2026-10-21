"""Owner access must not imply fabricated assessment capability."""

from httpx import AsyncClient


async def test_text_answer_does_not_invent_band_or_pronunciation(client: AsyncClient) -> None:
    response = await client.post("/api/ielts/evaluate", json={"answer": "because " * 200})
    assert response.status_code == 200
    data = response.json()
    assert data["pronunciation_score"] is None
    assert data["estimated_band"] is None
    assert "not" in data["disclaimer"].lower() or "bajarilmagan" in data["disclaimer"].lower()


async def test_offline_owner_grant_and_revoke_do_not_bypass_api_security(
    app, client: AsyncClient
) -> None:
    from ezo_api.owner_admin import change_owner_role

    services = app.state.services
    await client.get("/api/me")
    assert (await client.get("/api/admin/governance/status")).status_code == 403
    await change_owner_role(services.db, services.settings.owner_email, grant=True)
    response = await client.get("/api/admin/governance/status")
    assert response.status_code == 200
    assert response.json()["autonomous_deployment"] is False
    assert (await client.get("/api/student/status")).status_code == 200
    assert (await client.get("/api/presentations/themes")).status_code == 200
    assert (await client.get("/api/office/templates")).status_code == 200
    assert (await client.get("/api/personal/profile")).status_code == 200
    await change_owner_role(services.db, services.settings.owner_email, grant=False)
    assert (await client.get("/api/admin/governance/status")).status_code == 403
