import pytest

from ezo_api.providers.errors import ProviderErrorKind
from ezo_api.providers.offline import OfflineProvider
from ezo_api.providers.router import (
    AllProvidersFailedError,
    ModelRouter,
    RoutingConfigError,
    StreamInterruptedError,
    load_routing_config,
    parse_routing_config,
)
from ezo_api.providers.types import ChatMessage, ChatRequest, StreamEnd, TextDelta
from ezo_api.settings import API_DIR
from tests.fakes import FakeProvider

CONFIG = parse_routing_config(
    {
        "routes": {
            "chat": {
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-5-5", "effort": "low"},
                    {"provider": "openai", "model": "gpt-fast"},
                ]
            },
            "coding": {"candidates": [{"provider": "openai", "model": "gpt-code"}]},
        }
    }
)
REQUEST = ChatRequest(model="", messages=[ChatMessage("user", "salom")])


async def collect(router: ModelRouter, route: str) -> tuple[str, list[object]]:
    routed = router.open(route)
    events = [event async for event in routed.stream(REQUEST)]
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    return text, [routed, events]


def test_shipped_models_toml_is_valid() -> None:
    config = load_routing_config(API_DIR / "config" / "models.toml")
    assert {"chat", "reasoning", "coding", "long_context", "vision"} <= set(config.routes)


async def test_uses_first_configured_candidate_with_its_model_and_effort() -> None:
    anthropic = FakeProvider(name="anthropic", reply="hi there")
    router = ModelRouter(CONFIG, {"anthropic": anthropic}, OfflineProvider())
    text, _ = await collect(router, "chat")
    assert text == "hi there"
    assert anthropic.requests[0].model == "claude-haiku-5-5"
    assert anthropic.requests[0].effort == "low"


async def test_falls_back_to_next_provider_before_first_token() -> None:
    anthropic = FakeProvider(name="anthropic", fail_with=ProviderErrorKind.RATE_LIMIT)
    openai = FakeProvider(name="openai", reply="fallback works")
    router = ModelRouter(CONFIG, {"anthropic": anthropic, "openai": openai}, OfflineProvider())
    text, (routed, events) = await collect(router, "chat")
    assert text == "fallback works"
    assert [a.status for a in routed.attempts] == ["failed", "ok"]
    assert routed.attempts[0].error_kind == "rate_limit"
    assert routed.selected.provider is openai
    assert isinstance(events[-1], StreamEnd)


async def test_all_failures_raise_with_attempts() -> None:
    router = ModelRouter(
        CONFIG,
        {
            "anthropic": FakeProvider(name="anthropic", fail_with=ProviderErrorKind.AUTH),
            "openai": FakeProvider(name="openai", fail_with=ProviderErrorKind.UNAVAILABLE),
        },
        OfflineProvider(),
    )
    with pytest.raises(AllProvidersFailedError) as info:
        await collect(router, "chat")
    assert [a.error_kind for a in info.value.attempts] == ["auth", "unavailable"]


async def test_failure_after_partial_output_is_not_retried() -> None:
    flaky = FakeProvider(name="anthropic", reply="one two three", fail_after_chunks=2)
    backup = FakeProvider(name="openai", reply="never used")
    router = ModelRouter(CONFIG, {"anthropic": flaky, "openai": backup}, OfflineProvider())
    with pytest.raises(StreamInterruptedError):
        await collect(router, "chat")
    assert backup.requests == []


async def test_unexpected_exceptions_become_provider_errors() -> None:
    class Broken(FakeProvider):
        async def stream_chat(self, request):  # type: ignore[no-untyped-def,override]
            raise RuntimeError("boom")
            yield  # pragma: no cover

    backup = FakeProvider(name="openai", reply="ok")
    router = ModelRouter(
        CONFIG, {"anthropic": Broken(name="anthropic"), "openai": backup}, OfflineProvider()
    )
    text, (routed, _) = await collect(router, "chat")
    assert text == "ok"
    assert routed.attempts[0].error_kind == "unknown"


def test_preferred_provider_moves_first() -> None:
    router = ModelRouter(
        CONFIG,
        {"anthropic": FakeProvider(name="anthropic"), "openai": FakeProvider(name="openai")},
        OfflineProvider(),
        preferred_provider="openai",
    )
    assert [c.provider.name for c in router.candidates("chat")] == ["openai", "anthropic"]


def test_unknown_route_uses_chat_and_missing_provider_falls_back_to_chat() -> None:
    router = ModelRouter(CONFIG, {"anthropic": FakeProvider(name="anthropic")}, OfflineProvider())
    assert router.candidates("does-not-exist")[0].model == "claude-haiku-5-5"
    # "coding" lists only openai, which is not configured -> chat route
    assert router.candidates("coding")[0].provider.name == "anthropic"


def test_no_providers_means_offline() -> None:
    router = ModelRouter(CONFIG, {}, OfflineProvider())
    assert router.is_offline
    assert router.candidates("chat")[0].provider.name == "offline"


def test_provider_not_in_config_is_a_clear_error() -> None:
    router = ModelRouter(CONFIG, {"gemini": FakeProvider(name="gemini")}, OfflineProvider())
    with pytest.raises(RoutingConfigError, match="gemini"):
        router.candidates("chat")


@pytest.mark.parametrize(
    "raw",
    [
        {"routes": {}},
        {"routes": {"chat": {"candidates": [{"provider": "openai"}]}}},
        {"routes": {"chat": {"candidates": [{"provider": "o", "model": "m", "effort": "max"}]}}},
    ],
)
def test_invalid_configs_are_rejected(raw: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(RoutingConfigError):
        parse_routing_config(raw)
