"""PostgreSQL + pgvector store (used automatically when the extension is installed).

Vectors live in the `pgvector_entries` table created by migration 0002.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.knowledge.vectorstores.base import (
    OwnerType,
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorStore,
)


def _literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class PgVectorStore(VectorStore):
    name = "pgvector"

    async def upsert(self, session: AsyncSession, records: Sequence[VectorRecord]) -> None:
        for r in records:
            await session.execute(
                text(
                    """
                    INSERT INTO pgvector_entries
                        (id, user_id, owner_type, owner_id, document_id, project_id, model, dim,
                         embedding)
                    VALUES (:id, :user_id, :owner_type, :owner_id, :document_id, :project_id,
                            :model, :dim, CAST(:embedding AS vector))
                    ON CONFLICT (owner_type, owner_id, model) DO UPDATE
                    SET embedding = EXCLUDED.embedding, dim = EXCLUDED.dim,
                        document_id = EXCLUDED.document_id, project_id = EXCLUDED.project_id
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": r.user_id,
                    "owner_type": r.owner_type,
                    "owner_id": r.owner_id,
                    "document_id": r.document_id,
                    "project_id": r.project_id,
                    "model": r.model,
                    "dim": len(r.vector),
                    "embedding": _literal(r.vector),
                },
            )

    async def delete_owners(
        self, session: AsyncSession, owner_type: OwnerType, owner_ids: Sequence[uuid.UUID]
    ) -> None:
        if owner_ids:
            await session.execute(
                text(
                    "DELETE FROM pgvector_entries "
                    "WHERE owner_type = :owner_type AND owner_id = ANY(:ids)"
                ),
                {"owner_type": owner_type, "ids": list(owner_ids)},
            )

    async def delete_document(self, session: AsyncSession, document_id: uuid.UUID) -> None:
        await session.execute(
            text("DELETE FROM pgvector_entries WHERE document_id = :document_id"),
            {"document_id": document_id},
        )

    async def search(
        self,
        session: AsyncSession,
        query: Sequence[float],
        where: VectorFilter,
        limit: int,
    ) -> list[VectorHit]:
        params: dict[str, Any] = {
            "q": _literal(query),
            "user_id": where.user_id,
            "owner_type": where.owner_type,
            "model": where.model,
            "dim": len(query),
            "project_id": where.project_scope,
            "limit": limit,
        }
        documents = ""
        if where.document_ids is not None:
            documents = "AND document_id = ANY(:document_ids)"
            params["document_ids"] = list(where.document_ids)
        rows = await session.execute(
            text(
                f"""
                SELECT owner_id, 1 - (embedding <=> CAST(:q AS vector)) AS score
                FROM pgvector_entries
                WHERE user_id = :user_id AND owner_type = :owner_type AND model = :model
                  AND dim = :dim
                  AND (project_id IS NULL OR project_id = :project_id)
                  {documents}
                ORDER BY embedding <=> CAST(:q AS vector)
                LIMIT :limit
                """  # noqa: S608 (only a fixed fragment is interpolated)
            ),
            params,
        )
        return [VectorHit(owner_id=row.owner_id, score=float(row.score)) for row in rows]

    async def count(self, session: AsyncSession, user_id: uuid.UUID, owner_type: OwnerType) -> int:
        total = await session.scalar(
            text(
                "SELECT count(*) FROM pgvector_entries "
                "WHERE user_id = :user_id AND owner_type = :owner_type"
            ),
            {"user_id": user_id, "owner_type": owner_type},
        )
        return int(total or 0)
