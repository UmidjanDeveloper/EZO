"""Test doubles for model providers, web search and HTTP."""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image

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
from ezo_api.visual.base import (
    GeneratedImage,
    ImageEditProvider,
    ImageError,
    ImageProvider,
    ImageRequest,
)
from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
)

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


class FakeVoice(SpeechToTextProvider, TextToSpeechProvider):
    """Voice provider for tests: returns a fixed transcript / audio or fails with `fail_kind`."""

    def __init__(
        self, name: str, transcript: str = "Salom EZO", fail_kind: str | None = None
    ) -> None:
        self.name = name
        self.transcript = transcript
        self.fail_kind = fail_kind
        self.calls: list[tuple[str, int, str | None]] = []

    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> Transcript:
        self.calls.append(("stt", len(audio), language))
        if self.fail_kind:
            raise VoiceError(self.fail_kind, f"{self.name}: failed")  # type: ignore[arg-type]
        return Transcript(text=self.transcript, language=language or "uz", provider=self.name)

    async def synthesize(self, text: str, language: str | None) -> SpeechAudio:
        self.calls.append(("tts", len(text), language))
        if self.fail_kind:
            raise VoiceError(self.fail_kind, f"{self.name}: failed")  # type: ignore[arg-type]
        return SpeechAudio(data=b"ID3fake-mp3", mime_type="audio/mpeg", provider=self.name)


def png_bytes(width: int, height: int, color: str = "#3366cc") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class FakeImages(ImageProvider, ImageEditProvider):
    """Returns a solid-colour image of the requested proportions, or fails in a chosen way."""

    name: str = "fake-images"
    model: str = "fake-image-1"
    fail_with: str | None = None
    data: bytes | None = None
    """Return these bytes instead of a real image (to test validation)."""
    requests: list[ImageRequest] = field(default_factory=list)
    edits: list[tuple[bytes, ImageRequest]] = field(default_factory=list)

    def _image(self, request: ImageRequest) -> GeneratedImage:
        if self.fail_with is not None:
            raise ImageError(self.fail_with, f"scripted {self.fail_with}")  # type: ignore[arg-type]
        width, height = (int(v) * 128 for v in request.aspect_ratio.split(":"))
        return GeneratedImage(
            data=self.data if self.data is not None else png_bytes(width, height),
            mime_type="image/png",
            provider=self.name,
            model=self.model,
            revised_prompt=f"revised: {request.prompt[:40]}",
        )

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        self.requests.append(request)
        return self._image(request)

    async def edit(self, image: bytes, mime_type: str, request: ImageRequest) -> GeneratedImage:
        self.edits.append((image, request))
        result = self._image(request)
        return GeneratedImage(
            png_bytes(*Image.open(io.BytesIO(image)).size, color="#112244"),
            result.mime_type,
            result.provider,
            result.model,
        )
