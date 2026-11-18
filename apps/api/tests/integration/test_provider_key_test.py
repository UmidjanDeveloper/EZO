"""The owner's "test keys" button makes one tiny real request per configured provider."""

from httpx import AsyncClient

from ezo_api.providers.errors import ProviderErrorKind
from tests.fakes import FakeProvider


async def test_each_configured_provider_is_probed_and_the_outcome_remembered(
    client: AsyncClient, fake_anthropic: FakeProvider, fake_openai: FakeProvider
) -> None:
    fake_openai.fail_with = ProviderErrorKind.AUTH
    response = await client.post("/api/status/providers/test")
    assert response.status_code == 200
    body = response.json()
    assert body["offline"] is False
    assert {p["name"]: p["result"] for p in body["providers"]} == {
        "anthropic": "ok",
        "openai": "auth",
    }
    # A tiny request, not a conversation.
    probe = fake_anthropic.requests[-1]
    assert probe.max_output_tokens <= 16 and len(probe.messages) == 1

    status = (await client.get("/api/status")).json()
    results = {p["name"]: p["last_result"] for p in status["providers"] if p["configured"]}
    assert results == {"anthropic": "ok", "openai": "auth"}

    # The key itself never appears in the answer.
    assert "key" not in str({p["name"]: p for p in body["providers"]}).replace("key_warning", "")
