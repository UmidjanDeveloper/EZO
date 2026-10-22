import asyncio

import pytest
from pydantic import ValidationError

from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.limits import CallBudget, LimitedModelProvider, UsageLimitError
from ezo_api.providers.registry import build_providers
from ezo_api.providers.types import ChatMessage, ChatRequest
from ezo_api.settings import Settings
from tests.fakes import FakeProvider


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


async def test_shared_budget_bounds_chat_embeddings_and_fallback_attempts() -> None:
    raw = FakeProvider(supports_embeddings=True)
    budget = CallBudget(2, 1, 5)
    one = LimitedModelProvider(raw, budget, settings(EZO_PROVIDER_MAX_OUTPUT_TOKENS=50))
    two = LimitedModelProvider(FakeProvider(), budget, settings())
    await one.chat(ChatRequest("model", [ChatMessage("user", "Salom")], max_output_tokens=100))
    assert raw.requests[0].max_output_tokens == 50
    await one.embed(["one"], "embedding")
    with pytest.raises(ProviderError) as caught:
        await two.chat(ChatRequest("model", []))
    assert caught.value.kind == ProviderErrorKind.RATE_LIMIT
    assert not two.inner.requests  # type: ignore[attr-defined]


async def test_oversized_input_never_reaches_vendor_or_consumes_budget() -> None:
    raw = FakeProvider()
    budget = CallBudget(1, 1, 5)
    provider = LimitedModelProvider(raw, budget, settings(EZO_PROVIDER_MAX_INPUT_CHARS=1000))
    with pytest.raises(ProviderError):
        await provider.chat(ChatRequest("model", [ChatMessage("user", "x" * 1001)]))
    with pytest.raises(ProviderError):
        await provider.embed(["x"] * 65, "embedding")
    assert budget.remaining == 1 and raw.requests == []


async def test_deadline_includes_admission_wait_and_releases_cancelled_slot() -> None:
    budget = CallBudget(5, 1, 0.03)
    entered = asyncio.Event()

    async def hold() -> None:
        async with budget.admit():
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(hold())
    await entered.wait()
    with pytest.raises(TimeoutError):
        await task
    async with budget.admit():
        assert budget.remaining == 3
    async with budget.slots:
        with pytest.raises(TimeoutError):
            async with budget.admit():
                pytest.fail("admitted while slot occupied")
    assert budget.remaining == 3


async def test_failed_call_is_not_refunded() -> None:
    raw = FakeProvider(fail_with=ProviderErrorKind.AUTH)
    provider = LimitedModelProvider(raw, CallBudget(1, 1, 5), settings())
    with pytest.raises(ProviderError):
        await provider.chat(ChatRequest("m", []))
    with pytest.raises(UsageLimitError):
        async with provider.budget.admit():
            pytest.fail("budget refunded")


def test_existing_adapters_are_retained_and_share_budget() -> None:
    providers = build_providers(settings(OPENAI_API_KEY="fixture", GEMINI_API_KEY="fixture"))
    assert set(providers) == {"openai", "gemini"}
    assert all(isinstance(p, LimitedModelProvider) for p in providers.values())
    assert providers["openai"].budget is providers["gemini"].budget  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "name",
    [
        "EZO_PROVIDER_CONCURRENCY",
        "EZO_PROVIDER_CALLS_PER_DAY",
        "EZO_VOICE_CALLS_PER_DAY",
        "EZO_PROVIDER_MAX_OUTPUT_TOKENS",
    ],
)
def test_cannot_disable_bounds_with_zero(name: str) -> None:
    with pytest.raises(ValidationError):
        settings(**{name: 0})


async def test_cancelled_model_stream_closes_vendor_and_releases_slot() -> None:
    from ezo_api.providers.types import TextDelta

    class Streaming(FakeProvider):
        closed = False

        async def stream_chat(self, request):
            try:
                yield TextDelta("partial")
                await asyncio.Event().wait()
            finally:
                self.closed = True

    raw = Streaming()
    budget = CallBudget(2, 1, 5)
    provider = LimitedModelProvider(raw, budget, settings())
    stream = provider.stream_chat(ChatRequest("m", []))
    assert (await anext(stream)).text == "partial"
    await stream.aclose()
    assert raw.closed and not budget.slots.locked()
