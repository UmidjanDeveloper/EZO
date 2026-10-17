"""VectorStore interface.

Callers never touch pgvector or SQL directly: they upsert vectors for "owners"
(knowledge chunks or memories) and search with filters.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

OwnerType = str  # "chunk" | "memory"


@dataclass(frozen=True, slots=True)
class VectorRecord:
    owner_type: OwnerType
    owner_id: uuid.UUID
    user_id: uuid.UUID
    model: str
    vector: Sequence[float]
    document_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class VectorFilter:
    user_id: uuid.UUID
    owner_type: OwnerType
    model: str
    project_scope: uuid.UUID | None = None
    """Include global entries (no project) plus entries of this project."""
    document_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True, slots=True)
class VectorHit:
    owner_id: uuid.UUID
    score: float
    """Cosine similarity, -1..1 (higher is closer)."""


class VectorStore(ABC):
    name: str

    @abstractmethod
    async def upsert(self, session: AsyncSession, records: Sequence[VectorRecord]) -> None: ...

    @abstractmethod
    async def delete_owners(
        self, session: AsyncSession, owner_type: OwnerType, owner_ids: Sequence[uuid.UUID]
    ) -> None: ...

    @abstractmethod
    async def delete_document(self, session: AsyncSession, document_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def search(
        self,
        session: AsyncSession,
        query: Sequence[float],
        where: VectorFilter,
        limit: int,
    ) -> list[VectorHit]: ...

    @abstractmethod
    async def count(
        self, session: AsyncSession, user_id: uuid.UUID, owner_type: OwnerType
    ) -> int: ...
