"""Test doubles for model providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.types import (
    Capability,
    ChatRequest,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)


@dataclass
class FakeProvider(ModelProvider):
    """Streams a scripted reply, or fails in a chosen way."""

    name: str = "fake"
    reply: str = "Salom! Men EZO."
    fail_with: ProviderErrorKind | None = None
    fail_after_chunks: int | None = None
    finish_reason: str | None = "end_turn"
    requests: list[ChatRequest] = field(default_factory=list)

    display_name = "Fake"
    capabilities = frozenset({Capability.CHAT, Capability.STREAMING})

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        if self.fail_with is not None and self.fail_after_chunks is None:
            raise ProviderError(self.name, self.fail_with, "scripted failure", 500)
        words = self.reply.split(" ")
        for index, word in enumerate(words):
            if self.fail_after_chunks is not None and index >= self.fail_after_chunks:
                raise ProviderError(
                    self.name, self.fail_with or ProviderErrorKind.UNAVAILABLE, "dropped", None
                )
            yield TextDelta(word if index == 0 else " " + word)
        yield StreamEnd(model=request.model, usage=Usage(12, 7), finish_reason=self.finish_reason)
