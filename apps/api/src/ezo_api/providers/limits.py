"""Process-local admission bounds; not a durable monetary spending limit."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Literal

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.types import ChatRequest, StreamEvent
from ezo_api.settings import Settings


class UsageLimitError(RuntimeError):
    pass


class CallBudget:
    def __init__(self, calls: int, concurrency: int, timeout: float) -> None:
        self.calls, self.timeout = calls, timeout
        self.remaining = calls
        self.started = time.monotonic()
        self.slots = asyncio.Semaphore(concurrency)

    @asynccontextmanager
    async def admit(self) -> AsyncIterator[None]:
        async with asyncio.timeout(self.timeout):
            async with self.slots:
                now = time.monotonic()
                if now - self.started >= 86400:
                    self.started, self.remaining = now, self.calls
                if self.remaining <= 0:
                    raise UsageLimitError("Process-local provider call budget exhausted.")
                # No await between checking and reserving; failed calls also consume budget.
                self.remaining -= 1
                yield


class LimitedModelProvider(ModelProvider):
    def __init__(self, provider: ModelProvider, budget: CallBudget, settings: Settings) -> None:
        self.inner, self.budget, self.settings = provider, budget, settings
        self.name, self.display_name = provider.name, provider.display_name
        self.capabilities = provider.capabilities

    def _check_input(self, count: int) -> None:
        if count > self.settings.provider_max_input_chars:
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_REQUEST, "Provider input limit exceeded."
            )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self._check_input(len(request.system or "") + sum(len(m.content) for m in request.messages))
        bounded = replace(
            request,
            max_output_tokens=min(
                request.max_output_tokens, self.settings.provider_max_output_tokens
            ),
        )
        try:
            async with self.budget.admit():
                stream = self.inner.stream_chat(bounded)
                try:
                    async for event in stream:
                        yield event
                finally:
                    close = getattr(stream, "aclose", None)
                    if close is not None:
                        await close()
        except UsageLimitError:
            raise ProviderError(
                self.name, ProviderErrorKind.RATE_LIMIT, "Provider call budget exhausted."
            ) from None
        except TimeoutError:
            raise ProviderError(
                self.name, ProviderErrorKind.TIMEOUT, "Provider operation deadline exceeded."
            ) from None

    async def embed(
        self, texts: Sequence[str], model: str, purpose: Literal["document", "query"] = "document"
    ) -> list[list[float]]:
        self._check_input(sum(len(t) for t in texts))
        if len(texts) > 64:
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_REQUEST, "Embedding batch limit exceeded."
            )
        try:
            async with self.budget.admit():
                return await self.inner.embed(texts, model, purpose)
        except UsageLimitError:
            raise ProviderError(
                self.name, ProviderErrorKind.RATE_LIMIT, "Provider call budget exhausted."
            ) from None
        except TimeoutError:
            raise ProviderError(
                self.name, ProviderErrorKind.TIMEOUT, "Provider operation deadline exceeded."
            ) from None
