from httpx import AsyncClient

from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def test_memory_is_captured_and_retrieved_in_later_conversations(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    await stream_chat(client, message="Ezo, eslab qol: men minimalist dizaynni yoqtiraman.")
    memories = (await client.get("/api/memories")).json()
    assert len(memories) == 1
    assert memories[0]["content"] == "men minimalist dizaynni yoqtiraman."
    assert memories[0]["memory_type"] == "profile"
    assert memories[0]["source"] == "auto"

    # A brand-new conversation still gets the profile memory in its prompt.
    events = await stream_chat(client, message="Sayt dizayni haqida maslahat ber")
    assert "minimalist dizaynni" in (fake_anthropic.requests[-1].system or "")
    assert events[-1][1]["message"]["metadata"]["memories_used"] == [memories[0]["id"]]


async def test_repeated_statements_reinforce_instead_of_duplicating(client: AsyncClient) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    await stream_chat(client, message="I prefer dark mode interfaces.")
    await stream_chat(client, message="I prefer dark mode interfaces.")
    memories = (await client.get("/api/memories")).json()
    assert len(memories) == 1
    assert memories[0]["importance"] > 0.65


async def test_sensitive_and_ordinary_messages_are_not_stored(client: AsyncClient) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    await stream_chat(client, message="Remember that my password is hunter2.")
    await stream_chat(client, message="What is the capital of France?")
    assert (await client.get("/api/memories")).json() == []


async def test_auto_memory_can_be_disabled(client: AsyncClient) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    response = await client.patch("/api/me/preferences", json={"auto_memory": False})
    assert response.json()["preferences"]["auto_memory"] is False
    await stream_chat(client, message="Eslab qol: men choyni yaxshi ko'raman.")
    assert (await client.get("/api/memories")).json() == []


async def test_manual_memory_crud(client: AsyncClient) -> None:
    created = await client.post(
        "/api/memories", json={"content": "Prefers concise answers", "category": "preference"}
    )
    assert created.status_code == 201
    memory_id = created.json()["id"]
    assert created.json()["source"] == "user"

    updated = await client.patch(f"/api/memories/{memory_id}", json={"importance": 0.95})
    assert updated.json()["importance"] == 0.95

    assert (await client.delete(f"/api/memories/{memory_id}")).status_code == 204
    assert (await client.get("/api/memories")).json() == []


async def test_delete_all_requires_confirmation(client: AsyncClient) -> None:
    await client.post("/api/memories", json={"content": "Likes tea"})
    assert (await client.delete("/api/memories")).status_code == 422
    assert (await client.delete("/api/memories?confirm=true")).status_code == 204
    assert (await client.get("/api/memories")).json() == []


async def test_project_memories_stay_in_their_project(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    project = (await client.post("/api/projects", json={"name": "EZO website"})).json()
    await stream_chat(
        client, message="We decided to use a dark blue color palette.", project_id=project["id"]
    )
    memories = (await client.get(f"/api/memories?project_id={project['id']}")).json()
    assert memories[0]["memory_type"] == "project"

    # Outside the project the decision is not injected.
    await stream_chat(client, message="Which color palette should we use?")
    assert "dark blue" not in (fake_anthropic.requests[-1].system or "")
    # Inside the project it is.
    await stream_chat(
        client, message="Which color palette should we use?", project_id=project["id"]
    )
    assert "dark blue" in (fake_anthropic.requests[-1].system or "")


# --- F18: consent controls recall as well as capture ------------------------------------


async def _manual_memory_then_chat(client: AsyncClient, fake: FakeProvider) -> str:
    await client.post("/api/memories", json={"content": "Prefers minimalist teal designs"})
    await stream_chat(client, message="Sayt dizayni haqida maslahat ber, minimalist teal")
    return fake.requests[-1].system or ""


async def test_revoking_consent_stops_recall_of_saved_memories(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    assert "minimalist teal" in await _manual_memory_then_chat(client, fake_anthropic)

    revoked = await client.post(
        "/api/personal/consent", json={"consent": False, "auto_memory": False}
    )
    assert revoked.json()["memory_recall"] is False
    assert "no longer used" in revoked.json()["message"]
    await stream_chat(client, message="Sayt dizayni haqida yana maslahat ber, minimalist teal")
    assert "minimalist teal" not in (fake_anthropic.requests[-1].system or "")
    # The memory itself is kept for the user to see, export or delete.
    assert [m["content"] for m in (await client.get("/api/memories")).json()] == [
        "Prefers minimalist teal designs"
    ]
    profile = (await client.get("/api/personal/profile")).json()
    assert profile["memory_recall"] is False and profile["auto_memory"] is False


async def test_recall_can_be_kept_explicitly_without_capture(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    kept = await client.post(
        "/api/personal/consent", json={"consent": False, "auto_memory": True, "recall": True}
    )
    assert kept.json() | {"message": ""} == {
        "memory_consent": False,
        "auto_memory": False,  # capture always needs consent
        "memory_recall": True,
        "message": "",
    }
    assert "minimalist teal" in await _manual_memory_then_chat(client, fake_anthropic)
    await stream_chat(client, message="Eslab qol: men choyni yaxshi ko'raman.")
    assert len((await client.get("/api/memories")).json()) == 1  # nothing captured


async def test_preferences_endpoint_cannot_bypass_consent(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    response = await client.patch(
        "/api/me/preferences", json={"memory_consent": False, "auto_memory": True}
    )
    prefs = response.json()["preferences"]
    assert prefs["memory_consent"] is False and prefs["auto_memory"] is False
    assert prefs["memory_recall"] is None  # follows consent -> off
    assert "minimalist teal" not in await _manual_memory_then_chat(client, fake_anthropic)


async def test_without_consent_saved_memories_are_not_recalled_by_default(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    assert "minimalist teal" not in await _manual_memory_then_chat(client, fake_anthropic)
    await client.patch("/api/me/preferences", json={"memory_recall": True})
    await stream_chat(client, message="Yana dizayn maslahati: minimalist teal")
    assert "minimalist teal" in (fake_anthropic.requests[-1].system or "")
