"""Test doubles for model providers, web search and HTTP."""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

from ezo_api.memory.scoring import stem_tokens
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
from ezo_api.tools.web_search import WebResult, WebSearchError, WebSearchProvider

EMBED_DIM = 64


def fake_embedding(text: str) -> list[float]:
    """Deterministic bag-of-stems vector: texts sharing words are similar."""
    vector = [0.0] * EMBED_DIM
    for stem in stem_tokens(text):
        bucket = int(hashlib.sha256(stem.encode()).hexdigest(), 16) % EMBED_DIM
        vector[bucket] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


@dataclass
class FakeProvider(ModelProvider):
    """Streams a scripted reply, or fails in a chosen way."""

    name: str = "fake"
    reply: str = "Salom! Men EZO."
    fail_with: ProviderErrorKind | None = None
    fail_after_chunks: int | None = None
    finish_reason: str | None = "end_turn"
    requests: list[ChatRequest] = field(default_factory=list)
    supports_embeddings: bool = False
    embed_fail: bool = False
    embed_calls: int = 0
    replies: list[str] = field(default_factory=list)
    """If set, consumed one per request before falling back to `reply`."""

    display_name = "Fake"

    @property
    def capabilities(self) -> frozenset[Capability]:  # type: ignore[override]
        caps = {Capability.CHAT, Capability.STREAMING}
        if self.supports_embeddings:
            caps.add(Capability.EMBEDDINGS)
        return frozenset(caps)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        if self.fail_with is not None and self.fail_after_chunks is None:
            raise ProviderError(self.name, self.fail_with, "scripted failure", 500)
        reply = self.replies.pop(0) if self.replies else self.reply
        words = reply.split(" ")
        for index, word in enumerate(words):
            if self.fail_after_chunks is not None and index >= self.fail_after_chunks:
                raise ProviderError(
                    self.name, self.fail_with or ProviderErrorKind.UNAVAILABLE, "dropped", None
                )
            yield TextDelta(word if index == 0 else " " + word)
        yield StreamEnd(model=request.model, usage=Usage(12, 7), finish_reason=self.finish_reason)

    async def embed(
        self,
        texts: Sequence[str],
        model: str,
        purpose: Literal["document", "query"] = "document",
    ) -> list[list[float]]:
        if not self.supports_embeddings:
            return await super().embed(texts, model, purpose)
        self.embed_calls += 1
        if self.embed_fail:
            raise ProviderError(self.name, ProviderErrorKind.RATE_LIMIT, "no quota", 429)
        return [fake_embedding(text) for text in texts]


@dataclass
class FakeWebSearch(WebSearchProvider):
    results: list[WebResult] = field(default_factory=list)
    error: str | None = None
    queries: list[str] = field(default_factory=list)
    name: str = "fake-search"

    async def search(
        self, query: str, max_results: int = 5, recent: bool = False
    ) -> list[WebResult]:
        self.queries.append(query)
        if self.error:
            raise WebSearchError(self.error)
        return self.results[:max_results]
