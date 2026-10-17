from httpx import AsyncClient

from ezo_api.providers.errors import ProviderErrorKind
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def test_provider_failure_falls_back(
    client: AsyncClient, fake_anthropic: FakeProvider, fake_openai: FakeProvider
) -> None:
    fake_anthropic.fail_with = ProviderErrorKind.RATE_LIMIT
    events = await stream_chat(client, message="Salom")
    done = events[-1][1]
    assert events[-1][0] == "done"
    assert done["message"]["content"] == fake_openai.reply
    assert done["run"]["provider"] == "openai"

    run = (await client.get(f"/api/agent-runs/{done['run']['id']}")).json()
    assert [(a["provider"], a["status"]) for a in run["attempts"]] == [
        ("anthropic", "failed"),
        ("openai", "ok"),
    ]


async def test_all_providers_failing_returns_error_event(
    client: AsyncClient, fake_anthropic: FakeProvider, fake_openai: FakeProvider
) -> None:
    fake_anthropic.fail_with = ProviderErrorKind.AUTH
    fake_openai.fail_with = ProviderErrorKind.AUTH
    events = await stream_chat(client, message="Salom")
    name, error = events[-1]
    assert name == "error"
    assert error["code"] == "all_providers_failed"
    assert "API key" in error["hint"]
    assert len(error["attempts"]) == 2

    run = (await client.get(f"/api/agent-runs/{error['run_id']}")).json()
    assert run["status"] == "failed"

    # The user message is kept; no assistant message was stored.
    conversation_id = events[0][1]["conversation_id"]
    messages = (await client.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert [m["role"] for m in messages] == ["user"]


async def test_non_streaming_error_is_502(
    client: AsyncClient, fake_anthropic: FakeProvider, fake_openai: FakeProvider
) -> None:
    fake_anthropic.fail_with = ProviderErrorKind.UNAVAILABLE
    fake_openai.fail_with = ProviderErrorKind.UNAVAILABLE
    response = await client.post("/api/chat", json={"message": "Salom"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "all_providers_failed"


async def test_interrupted_stream_reports_error(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "bir ikki uch to'rt"
    fake_anthropic.fail_after_chunks = 2
    events = await stream_chat(client, message="Salom")
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "stream_interrupted"


async def test_empty_and_truncated_replies_are_handled(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Uzun javob"
    fake_anthropic.finish_reason = "max_tokens"
    events = await stream_chat(client, message="Salom")
    done = events[-1][1]
    assert done["message"]["metadata"]["truncated"] is True
    assert "kesildi" in done["message"]["content"]

    fake_anthropic.reply = ""
    fake_anthropic.finish_reason = "refusal"
    events = await stream_chat(client, message="Salom")
    assert events[-1][1]["message"]["content"].startswith("Kechirasiz")
