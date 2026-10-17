"""Google Gemini adapter (official `google-genai` SDK)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

_THINKING_LEVELS = {
    "low": genai_types.ThinkingLevel.LOW,
    "medium": genai_types.ThinkingLevel.MEDIUM,
    "high": genai_types.ThinkingLevel.HIGH,
}


class GeminiProvider(ModelProvider):
    name = "gemini"
    display_name = "Google Gemini"
    capabilities = frozenset(
        {Capability.CHAT, Capability.STREAMING, Capability.REASONING, Capability.EMBEDDINGS}
    )

    def __init__(self, api_key: str, timeout: float, client: Any | None = None) -> None:
        self._client: Any = client or genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)),
        )

    def _contents(self, request: ChatRequest) -> list[genai_types.Content]:
        return [
            genai_types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[genai_types.Part(text=m.content)],
            )
            for m in normalize_turns(request.messages)
        ]

    def _config(self, request: ChatRequest) -> genai_types.GenerateContentConfig:
        thinking = (
            genai_types.ThinkingConfig(thinking_level=_THINKING_LEVELS[request.effort])
            if request.effort
            else None
        )
        return genai_types.GenerateContentConfig(
            system_instruction=request.system,
            max_output_tokens=request.max_output_tokens,
            thinking_config=thinking,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        usage = Usage()
        model = request.model
        finish_reason: str | None = None
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=request.model,
                contents=self._contents(request),
                config=self._config(request),
            )
            async for chunk in stream:
                model = getattr(chunk, "model_version", None) or model
                meta = getattr(chunk, "usage_metadata", None)
                if meta is not None:
                    usage = Usage(
                        input_tokens=meta.prompt_token_count,
                        output_tokens=meta.candidates_token_count,
                    )
                for candidate in getattr(chunk, "candidates", None) or []:
                    if candidate.finish_reason:
                        finish_reason = str(getattr(candidate.finish_reason, "value", None) or "")
                    content = candidate.content
                    for part in content.parts if content and content.parts else []:
                        # Skip thought-summary parts; only the answer is shown.
                        if part.text and not getattr(part, "thought", False):
                            yield TextDelta(part.text)
        except genai_errors.APIError as exc:
            status = exc.code if isinstance(exc.code, int) else None
            raise ProviderError(self.name, kind_from_status(status), str(exc), status) from exc
        except TimeoutError as exc:
            raise ProviderError(self.name, ProviderErrorKind.TIMEOUT, str(exc)) from exc
        except OSError as exc:
            raise ProviderError(self.name, ProviderErrorKind.UNAVAILABLE, str(exc)) from exc

        yield StreamEnd(model=model, usage=usage, finish_reason=finish_reason or None)

    async def embed(
        self,
        texts: Sequence[str],
        model: str,
        purpose: Literal["document", "query"] = "document",
    ) -> list[list[float]]:
        task = "RETRIEVAL_QUERY" if purpose == "query" else "RETRIEVAL_DOCUMENT"
        try:
            response = await self._client.aio.models.embed_content(
                model=model,
                contents=list(texts),
                config=genai_types.EmbedContentConfig(task_type=task),
            )
        except genai_errors.APIError as exc:
            status = exc.code if isinstance(exc.code, int) else None
            raise ProviderError(self.name, kind_from_status(status), str(exc), status) from exc
        except TimeoutError as exc:
            raise ProviderError(self.name, ProviderErrorKind.TIMEOUT, str(exc)) from exc
        except OSError as exc:
            raise ProviderError(self.name, ProviderErrorKind.UNAVAILABLE, str(exc)) from exc
        return [list(item.values or []) for item in response.embeddings or []]
