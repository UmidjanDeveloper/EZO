from httpx import AsyncClient

from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_streaming_chat_end_to_end(client: AsyncClient, fake_anthropic: FakeProvider) -> None:
    events = await stream_chat(client, message="Salom, qalaysan?")
    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    assert "delta" in names

    meta = events[0][1]
    assert meta["agent"] == "general" and meta["language"] == "uz"
    assert meta["created_conversation"] is True

    streamed = "".join(data["text"] for name, data in events if name == "delta")
    done = events[-1][1]
    assert done["message"]["content"] == streamed.strip() == fake_anthropic.reply
    assert done["run"]["provider"] == "anthropic"
    assert done["run"]["input_tokens"] == 12

    # The conversation and both messages are persisted.
    conversation_id = meta["conversation_id"]
    messages = (await client.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["metadata"]["provider"] == "anthropic"
    conversations = (await client.get("/api/conversations")).json()
    assert conversations[0]["title"] == "Salom, qalaysan?"


async def test_history_and_system_prompt_reach_the_provider(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    first = await stream_chat(client, message="Salom!")
    conversation_id = first[0][1]["conversation_id"]
    await stream_chat(client, message="Yana bir savol", conversation_id=conversation_id)

    request = fake_anthropic.requests[-1]
    assert [m.role for m in request.messages] == ["user", "assistant", "user"]
    assert request.messages[-1].content == "Yana bir savol"
    assert request.system and "You are EZO" in request.system


async def test_agent_routing_for_unavailable_agent(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    events = await stream_chat(client, message="Ezo, biznesim uchun SWOT tahlil qil.")
    meta = events[0][1]
    assert meta["intent"] == "business"
    assert meta["requested_agent"] == "business"
    assert meta["requested_agent_available"] is False
    assert meta["agent"] == "general"
    # The covering agent is told about the limitation, so it cannot pretend.
    assert "never invent market statistics" in (fake_anthropic.requests[-1].system or "")


async def test_routing_uses_route_specific_model(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await stream_chat(client, message="Ezo, GitHub projectimdagi bugni top.")
    # models.toml: coding -> anthropic claude-opus-5-5
    assert fake_anthropic.requests[-1].model == "claude-opus-5-5"
    await stream_chat(client, message="Salom")
    assert fake_anthropic.requests[-1].model == "claude-haiku-5-5"


async def test_non_streaming_chat(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "Hello, how are you?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["language"] == "en"
    assert body["message"]["role"] == "assistant"


async def test_agent_run_trace_is_recorded(client: AsyncClient) -> None:
    events = await stream_chat(client, message="Salom")
    run_id = events[0][1]["run_id"]
    run = (await client.get(f"/api/agent-runs/{run_id}")).json()
    assert run["status"] == "completed"
    assert run["provider"] == "anthropic" and run["model"]
    assert run["latency_ms"] is not None
    step_names = [s["name"] for s in run["steps"]]
    for expected in (
        "detect_language",
        "classify_intent",
        "select_agent",
        "retrieve_memory",
        "compose_prompt",
        "generate",
        "verify",
        "save_memory",
    ):
        assert expected in step_names
    assert run["attempts"][0]["status"] == "ok"


async def test_validation_errors_are_readable(client: AsyncClient) -> None:
    response = await client.post("/api/chat/stream", json={"message": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["message"]

    too_long = await client.post("/api/chat/stream", json={"message": "x" * 20_000})
    assert too_long.status_code == 422
    assert "too long" in too_long.json()["error"]["message"]


async def test_unknown_conversation_is_404(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat/stream",
        json={"message": "hi", "conversation_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Conversation not found."


async def test_delete_conversation(client: AsyncClient) -> None:
    events = await stream_chat(client, message="Salom")
    conversation_id = events[0][1]["conversation_id"]
    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/api/conversations/{conversation_id}")).status_code == 404


async def test_status_reports_providers_agents_and_routes(client: AsyncClient) -> None:
    status = (await client.get("/api/status")).json()
    configured = {p["name"]: p["configured"] for p in status["providers"]}
    assert configured == {"anthropic": True, "openai": True, "gemini": False}
    assert status["offline_mode"] is False
    agents = {a["key"]: a["available"] for a in status["agents"]}
    assert agents["general"] is True and agents["presentation"] is True
    assert agents["document"] is True and agents["visual"] is True and agents["business"] is False
    assert status["routing"]["routes"]["chat"]["active_candidates"][0]["provider"] == "anthropic"


async def test_voice_channel_asks_for_spoken_replies(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    events = await stream_chat(client, message="Salom EZO", channel="voice")
    assert "Voice conversation" in (fake_anthropic.requests[-1].system or "")
    conversation_id = events[0][1]["conversation_id"]
    messages = (await client.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert messages[0]["metadata"]["channel"] == "voice"

    # Typed messages in the same conversation get the normal (text) style.
    await stream_chat(client, message="Endi yozaman", conversation_id=conversation_id)
    assert "Voice conversation" not in (fake_anthropic.requests[-1].system or "")


async def test_unknown_channel_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/chat/stream", json={"message": "hi", "channel": "fax"})
    assert response.status_code == 422


async def test_voice_language_hint_decides_ambiguous_turns(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    # "2026" carries no language; the recogniser heard Russian, so EZO answers in Russian.
    events = await stream_chat(client, message="2026", channel="voice", language_hint="ru")
    assert events[0][1]["language"] == "ru"
    # Clear words win over the hint, and typed text ignores it.
    events = await stream_chat(client, message="Salom, qalaysan?", channel="voice", language_hint="en")
    assert events[0][1]["language"] == "uz"
    events = await stream_chat(client, message="2026", channel="text", language_hint="ru")
    assert events[0][1]["language"] == "uz"
    bad = await client.post("/api/chat", json={"message": "x", "language_hint": "de"})
    assert bad.status_code == 422
