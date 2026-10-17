"""OpenAI adapter (official `openai` SDK, Chat Completions API)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import openai

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


class OpenAIProvider(ModelProvider):
    name = "openai"
    display_name = "OpenAI"
    capabilities = frozenset({Capability.CHAT, Capability.STREAMING, Capability.REASONING})

    def __init__(
        self,
        api_key: str,
        timeout: float,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._client: Any = client or openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2
        )

    def _params(self, request: ChatRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(
            {"role": m.role, "content": m.content} for m in normalize_turns(request.messages)
        )
        params: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_completion_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.effort:
            params["reasoning_effort"] = request.effort
        return params

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        usage = Usage()
        model = request.model
        finish_reason: str | None = None
        try:
            stream = await self._client.chat.completions.create(**self._params(request))
            async for chunk in stream:
                model = getattr(chunk, "model", None) or model
                if getattr(chunk, "usage", None):
                    usage = Usage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )
                for choice in getattr(chunk, "choices", None) or []:
                    text = getattr(choice.delta, "content", None)
                    if text:
                        yield TextDelta(text)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
        except openai.APITimeoutError as exc:
            raise ProviderError(self.name, ProviderErrorKind.TIMEOUT, str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(self.name, ProviderErrorKind.UNAVAILABLE, str(exc)) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                self.name, kind_from_status(exc.status_code), exc.message, exc.status_code
            ) from exc

        yield StreamEnd(model=model, usage=usage, finish_reason=finish_reason)
