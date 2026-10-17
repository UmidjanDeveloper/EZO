"""Reranking interface.

`PassthroughReranker` keeps the fused order. A model-based reranker (e.g. a
cross-encoder or a provider rerank API) can be added by implementing
`Reranker` and passing it to `Retriever`.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[T], texts: list[str]) -> list[T]: ...


class PassthroughReranker:
    async def rerank(self, query: str, candidates: list[T], texts: list[str]) -> list[T]:
        return candidates
