"""The ModelProvider interface.

To add a provider: subclass `ModelProvider`, implement `stream_chat`, and
register it in `providers/registry.py`. Nothing else in EZO needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from ezo_api.providers.errors import CapabilityNotAvailableError
from ezo_api.providers.types import (
    Capability,
    ChatRequest,
    ChatResult,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)


class ModelProvider(ABC):
    name: str
    display_name: str
    capabilities: frozenset[Capability]
    """Capabilities implemented by this adapter today (not just by the vendor)."""

    @abstractmethod
    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """Stream a reply as `TextDelta` events followed by exactly one `StreamEnd`.

        Implementations raise `ProviderError` on failure.
        """

    async def chat(self, request: ChatRequest) -> ChatResult:
        """Non-streaming convenience wrapper around `stream_chat`."""
        parts: list[str] = []
        end: StreamEnd | None = None
        async for event in self.stream_chat(request):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            else:
                end = event
        if end is None:
            end = StreamEnd(model=request.model, usage=Usage())
        return ChatResult(
            text="".join(parts), model=end.model, usage=end.usage, finish_reason=end.finish_reason
        )

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        raise CapabilityNotAvailableError(self.name, Capability.EMBEDDINGS, "Milestone 2")
