"""Vector stores and automatic selection."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.knowledge.vectorstores.base import VectorFilter, VectorHit, VectorRecord, VectorStore
from ezo_api.knowledge.vectorstores.local import LocalVectorStore
from ezo_api.knowledge.vectorstores.pgvector_store import PgVectorStore

logger = logging.getLogger(__name__)


class VectorStoreResolver:
    """Chooses the store once: pgvector when available (PostgreSQL), else local."""

    def __init__(self, preference: str) -> None:
        self.preference = preference
        self._store: VectorStore | None = None

    async def get(self, session: AsyncSession) -> VectorStore:
        if self._store is not None:
            return self._store
        store: VectorStore = LocalVectorStore()
        bind = session.get_bind()
        if self.preference != "local" and bind.dialect.name == "postgresql":
            exists = await session.scalar(text("SELECT to_regclass('public.pgvector_entries')"))
            if exists:
                store = PgVectorStore()
            elif self.preference == "pgvector":
                logger.warning(
                    "EZO_VECTOR_STORE=pgvector but the pgvector table is missing "
                    "(extension not installed?). Using the local vector store."
                )
        logger.info("Vector store: %s", store.name)
        self._store = store
        return store


__all__ = [
    "LocalVectorStore",
    "PgVectorStore",
    "VectorFilter",
    "VectorHit",
    "VectorRecord",
    "VectorStore",
    "VectorStoreResolver",
]
