"""Adapter tests with fake SDK clients (no network)."""

from __future__ import annotations

from types import SimpleNamespace as NS
from typing import Any

import anthropic
import pytest

from ezo_api.providers.anthropic_provider import SERVER_FALLBACK_BETA, AnthropicProvider
from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.gemini_provider import GeminiProvider
from ezo_api.providers.openai_provider import OpenAIProvider
from ezo_api.providers.types import ChatMessage, ChatRequest, StreamEnd, TextDelta, normalize_turns

REQUEST = ChatRequest(
    model="m",
    messages=[
        ChatMessage("user", "salom"),
        ChatMessage("assistant", "salom!"),
        ChatMessage("user", "qalaysan?"),
    ],
    system="You are EZO.",
    max_output_tokens=1000,
    effort="low",
)


async def drain(provider: Any, request: ChatRequest = REQUEST) -> tuple[str, StreamEnd]:
    text, end = "", None
    async for event in provider.stream_chat(request):
        if isinstance(event, TextDelta):
            text += event.text
        else:
            end = event
    assert end is not None
    return text, end


# --- Anthropic -----------------------------------------------------------------


class FakeAnthropicStream:
    def __init__(self, chunks: list[str], final: Any) -> None:
        self._chunks, self._final = chunks, final

    async def __aenter__(self) -> FakeAnthropicStream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self) -> Any:
        async def gen() -> Any:
            for chunk in self._chunks:
                yield chunk

        return gen()

    async def get_final_message(self) -> Any:
        return self._final


class FakeAnthropicClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error = error
        final = NS(
            model="claude-x", stop_reason="end_turn", usage=NS(input_tokens=11, output_tokens=5)
        )
        outer = self

        class Messages:
            def __init__(self, kind: str) -> None:
                self.kind = kind

            def stream(self, **params: Any) -> FakeAnthropicStream:
                outer.calls.append((self.kind, params))
                if outer.error:
                    raise outer.error
                return FakeAnthropicStream(["Sal", "om"], final)

        self.messages = Messages("messages")
        self.beta = NS(messages=Messages("beta"))


async def test_anthropic_maps_request_and_stream() -> None:
    client = FakeAnthropicClient()
    text, end = await drain(AnthropicProvider("k", 10, client=client))
    kind, params = client.calls[0]
    assert kind == "messages"
    assert params["system"] == "You are EZO."
    assert params["max_tokens"] == 1000
    assert params["output_config"] == {"effort": "low"}
    assert [m["role"] for m in params["messages"]] == ["user", "assistant", "user"]
    assert text == "Salom"
    assert end.usage.input_tokens == 11 and end.usage.output_tokens == 5
    assert end.finish_reason == "end_turn"


async def test_anthropic_uses_server_side_fallback_for_supported_models() -> None:
    client = FakeAnthropicClient()
    request = ChatRequest(model="claude-opus-5-5", messages=[ChatMessage("user", "hi")])
    await drain(AnthropicProvider("k", 10, client=client), request)
    kind, params = client.calls[0]
    assert kind == "beta"
    assert params["betas"] == [SERVER_FALLBACK_BETA]
    assert params["fallbacks"] == "default"


async def test_anthropic_maps_connection_errors() -> None:
    import httpx2

    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    with pytest.raises(ProviderError) as info:
        await drain(AnthropicProvider("k", 10, client=FakeAnthropicClient(error)))
    assert info.value.kind == ProviderErrorKind.UNAVAILABLE


# --- OpenAI --------------------------------------------------------------------


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        chunks = [
            NS(
                model="gpt-x", usage=None, choices=[NS(delta=NS(content="Hel"), finish_reason=None)]
            ),
            NS(
                model="gpt-x",
                usage=None,
                choices=[NS(delta=NS(content="lo"), finish_reason="stop")],
            ),
            NS(model="gpt-x", usage=NS(prompt_tokens=9, completion_tokens=2), choices=[]),
        ]
        outer = self

        async def create(**params: Any) -> Any:
            outer.params = params

            async def gen() -> Any:
                for chunk in chunks:
                    yield chunk

            return gen()

        self.chat = NS(completions=NS(create=create))


async def test_openai_maps_request_and_stream() -> None:
    client = FakeOpenAIClient()
    text, end = await drain(OpenAIProvider("k", 10, client=client))
    assert client.params["messages"][0] == {"role": "system", "content": "You are EZO."}
    assert client.params["max_completion_tokens"] == 1000
    assert client.params["reasoning_effort"] == "low"
    assert client.params["stream_options"] == {"include_usage": True}
    assert text == "Hello"
    assert end.model == "gpt-x"
    assert end.usage.input_tokens == 9
    assert end.finish_reason == "stop"


# --- Gemini --------------------------------------------------------------------


class FakeGeminiClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}
        outer = self

        def part(text: str, thought: bool = False) -> Any:
            return NS(text=text, thought=thought)

        chunks = [
            NS(
                model_version="gemini-x",
                usage_metadata=None,
                candidates=[
                    NS(
                        finish_reason=None,
                        content=NS(parts=[part("thinking...", True), part("Sa")]),
                    )
                ],
            ),
            NS(
                model_version="gemini-x",
                usage_metadata=NS(prompt_token_count=4, candidates_token_count=3),
                candidates=[NS(finish_reason=NS(value="STOP"), content=NS(parts=[part("lom")]))],
            ),
        ]

        async def generate_content_stream(**kwargs: Any) -> Any:
            outer.kwargs = kwargs

            async def gen() -> Any:
                for chunk in chunks:
                    yield chunk

            return gen()

        self.aio = NS(models=NS(generate_content_stream=generate_content_stream))


async def test_gemini_maps_roles_skips_thoughts_and_reads_usage() -> None:
    client = FakeGeminiClient()
    text, end = await drain(GeminiProvider("k", 10, client=client))
    roles = [c.role for c in client.kwargs["contents"]]
    assert roles == ["user", "model", "user"]
    assert client.kwargs["config"].system_instruction == "You are EZO."
    assert text == "Salom"
    assert end.usage.output_tokens == 3
    assert end.finish_reason == "STOP"


# --- shared --------------------------------------------------------------------


def test_normalize_turns_merges_and_trims() -> None:
    turns = normalize_turns(
        [
            ChatMessage("assistant", "leading assistant is dropped"),
            ChatMessage("user", "a"),
            ChatMessage("user", "b"),
            ChatMessage("assistant", "  "),
            ChatMessage("assistant", "c"),
        ]
    )
    assert [(t.role, t.content) for t in turns] == [("user", "a\n\nb"), ("assistant", "c")]
