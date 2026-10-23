"""Embedding service: picks one embedding model and batches requests.

All vectors in the index must come from the same model, so the first configured
provider with a key is used consistently (no silent per-request fallback that
would mix incompatible vectors).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.errors import ProviderError
from ezo_api.providers.router import CandidateConfig
from ezo_api.providers.types import Capability

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
MAX_INPUT_CHARS = 8_000


class EmbeddingError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    provider: ModelProvider
    model: str

    @property
    def key(self) -> str:
        """Stored with every vector, e.g. 'openai:text-embedding-3-small'."""
        return f"{self.provider.name}:{self.model}"


class EmbeddingService:
    def __init__(
        self, candidates: Sequence[CandidateConfig], providers: Mapping[str, ModelProvider]
    ) -> None:
        self.active: EmbeddingModel | None = None
        for candidate in candidates:
            provider = providers.get(candidate.provider)
            if provider is not None and Capability.EMBEDDINGS in provider.capabilities:
                self.active = EmbeddingModel(provider, candidate.model)
                break

    @property
    def available(self) -> bool:
        return self.active is not None

    @property
    def model_key(self) -> str | None:
        return self.active.key if self.active else None

    async def embed_documents(
        self, texts: Sequence[str], *, before_batch: Callable[[], Awaitable[None]] | None = None
    ) -> list[list[float]]:
        return await self._embed(texts, "document", before_batch=before_batch)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]

    async def _embed(
        self,
        texts: Sequence[str],
        purpose: str,
        *,
        before_batch: Callable[[], Awaitable[None]] | None = None,
    ) -> list[list[float]]:
        if self.active is None:
            raise EmbeddingError(
                "No embedding provider is configured.",
                "Add OPENAI_API_KEY or GEMINI_API_KEY to .env for semantic search.",
            )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [text[:MAX_INPUT_CHARS] for text in texts[start : start + BATCH_SIZE]]
            if before_batch is not None:
                await before_batch()
            try:
                result = await self.active.provider.embed(
                    batch,
                    self.active.model,
                    "query" if purpose == "query" else "document",
                )
            except ProviderError as exc:
                logger.warning("Embedding provider request failed (%s)", exc.kind.value)
                raise EmbeddingError(f"Embedding failed ({exc.kind.value}).", exc.hint) from exc
            if len(result) != len(batch) or any(not vector for vector in result):
                raise EmbeddingError("The embedding provider returned an unexpected result.")
            vectors.extend(result)
        return vectors
