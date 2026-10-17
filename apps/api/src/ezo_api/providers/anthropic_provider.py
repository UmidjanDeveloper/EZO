"""Anthropic Claude adapter (official `anthropic` SDK)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.errors import ProviderError, ProviderErrorKind, kind_from_status
from ezo_api.providers.types import (
    Capability,
    ChatRequest,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
    normalize_turns,
)

# Models that support the server-side refusal fallback (`fallbacks: "default"`):
# if a safety classifier declines, the API re-runs the request on a suitable
# fallback model inside the same call.
SERVER_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    display_name = "Anthropic Claude"
    capabilities = frozenset({Capability.CHAT, Capability.STREAMING, Capability.REASONING})

    def __init__(self, api_key: str, timeout: float, client: Any | None = None) -> None:
        self._client: Any = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=2
        )

    def _params(self, request: ChatRequest) -> dict[str, Any]:
        messages = [
            {"role": m.role, "content": m.content} for m in normalize_turns(request.messages)
        ]
        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": messages,
        }
        if request.system:
            params["system"] = request.system
        if request.effort:
            params["output_config"] = {"effort": request.effort}
        return params

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        params = self._params(request)
        try:
            if request.model in SERVER_FALLBACK_MODELS:
                manager = self._client.beta.messages.stream(
                    **params, betas=[SERVER_FALLBACK_BETA], fallbacks="default"
                )
            else:
                manager = self._client.messages.stream(**params)
            async with manager as stream:
                async for text in stream.text_stream:
                    if text:
                        yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.APITimeoutError as exc:
            raise ProviderError(self.name, ProviderErrorKind.TIMEOUT, str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(self.name, ProviderErrorKind.UNAVAILABLE, str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                self.name, kind_from_status(exc.status_code), exc.message, exc.status_code
            ) from exc

        usage = getattr(final, "usage", None)
        yield StreamEnd(
            model=getattr(final, "model", request.model),
            usage=Usage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            ),
            # "refusal" is surfaced as a finish reason; EzoCore turns an empty
            # refused reply into a polite message.
            finish_reason=getattr(final, "stop_reason", None),
        )
