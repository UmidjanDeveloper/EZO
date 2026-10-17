from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def test_project_crud_and_conversation_link(client: AsyncClient) -> None:
    created = await client.post(
        "/api/projects", json={"name": "Startup", "description": "Coffee subscription"}
    )
    assert created.status_code == 201
    project = created.json()

    events = await stream_chat(client, message="Salom", project_id=project["id"])
    conversation_id = events[0][1]["conversation_id"]
    listed = (await client.get(f"/api/conversations?project_id={project['id']}")).json()
    assert [c["id"] for c in listed] == [conversation_id]

    renamed = await client.patch(f"/api/projects/{project['id']}", json={"name": "Startup v2"})
    assert renamed.json()["name"] == "Startup v2"
    assert (await client.get("/api/projects")).json()[0]["name"] == "Startup v2"

    assert (await client.delete(f"/api/projects/{project['id']}")).status_code == 204
    # Conversations survive project deletion, unlinked.
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert conversation["project_id"] is None


async def test_project_name_is_required(client: AsyncClient) -> None:
    assert (await client.post("/api/projects", json={"name": ""})).status_code == 422


async def test_token_auth_mode(database_url: str) -> None:
    app: FastAPI = create_app(
        make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN="s3cret-token"),
        providers={"anthropic": FakeProvider(name="anthropic")},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/api/me")).status_code == 401
        bad = await ac.get("/api/me", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401
        ok = await ac.get("/api/me", headers={"Authorization": "Bearer s3cret-token"})
        assert ok.status_code == 200
    await app.state.services.db.dispose()


async def test_rate_limit(database_url: str) -> None:
    app = create_app(
        make_settings(database_url, EZO_RATE_LIMIT_CHAT=2),
        providers={"anthropic": FakeProvider(name="anthropic")},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(2):
            assert (await ac.post("/api/chat", json={"message": "hi"})).status_code == 200
        limited = await ac.post("/api/chat", json={"message": "hi"})
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
    await app.state.services.db.dispose()


async def test_offline_mode_without_providers(database_url: str) -> None:
    app = create_app(make_settings(database_url), providers={})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        events = await stream_chat(ac, message="Salom")
        assert "oflayn rejimda" in events[-1][1]["message"]["content"]
        assert (await ac.get("/api/status")).json()["offline_mode"] is True
    await app.state.services.db.dispose()


async def test_preferences_fixed_language(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    response = await client.patch("/api/me/preferences", json={"response_language": "en"})
    assert response.json()["preferences"]["response_language"] == "en"
    events = await stream_chat(client, message="Salom, qalaysan?")
    assert events[0][1]["language"] == "en"
    assert "Always answer in English" in (fake_anthropic.requests[-1].system or "")

    invalid = await client.patch("/api/me/preferences", json={"response_language": "de"})
    assert invalid.status_code == 422
