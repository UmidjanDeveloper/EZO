"""Portable vector store: vectors as JSON rows, cosine similarity with NumPy.

Works on SQLite and on PostgreSQL without pgvector. Exact search over the
user's vectors — fast enough for personal knowledge bases (tens of thousands
of chunks); larger installations should use pgvector.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import numpy as np
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import VectorEntry
from ezo_api.knowledge.vectorstores.base import (
    OwnerType,
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorStore,
)

MAX_SCAN = 50_000


class LocalVectorStore(VectorStore):
    name = "local"

    async def upsert(self, session: AsyncSession, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        for record in records:
            await session.execute(
                delete(VectorEntry).where(
                    VectorEntry.owner_type == record.owner_type,
                    VectorEntry.owner_id == record.owner_id,
                    VectorEntry.model == record.model,
                )
            )
        session.add_all(
            VectorEntry(
                user_id=r.user_id,
                owner_type=r.owner_type,
                owner_id=r.owner_id,
                document_id=r.document_id,
                project_id=r.project_id,
                model=r.model,
                dim=len(r.vector),
                vector=[float(x) for x in r.vector],
            )
            for r in records
        )
        await session.flush()

    async def delete_owners(
        self, session: AsyncSession, owner_type: OwnerType, owner_ids: Sequence[uuid.UUID]
    ) -> None:
        if owner_ids:
            await session.execute(
                delete(VectorEntry).where(
                    VectorEntry.owner_type == owner_type, VectorEntry.owner_id.in_(owner_ids)
                )
            )

    async def delete_document(self, session: AsyncSession, document_id: uuid.UUID) -> None:
        await session.execute(delete(VectorEntry).where(VectorEntry.document_id == document_id))

    async def search(
        self,
        session: AsyncSession,
        query: Sequence[float],
        where: VectorFilter,
        limit: int,
    ) -> list[VectorHit]:
        statement = select(VectorEntry.owner_id, VectorEntry.vector).where(
            VectorEntry.user_id == where.user_id,
            VectorEntry.owner_type == where.owner_type,
            VectorEntry.model == where.model,
            VectorEntry.dim == len(query),
            or_(VectorEntry.project_id.is_(None), VectorEntry.project_id == where.project_scope),
        )
        if where.document_ids is not None:
            statement = statement.where(VectorEntry.document_id.in_(where.document_ids))
        rows = (await session.execute(statement.limit(MAX_SCAN))).all()
        if not rows:
            return []
        matrix = np.asarray([row.vector for row in rows], dtype=np.float32)
        q = np.asarray(query, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(q) or 1.0)
        scores = (matrix @ q) / np.where(norms == 0, 1.0, norms)
        order = np.argsort(-scores)[:limit]
        return [VectorHit(owner_id=rows[i].owner_id, score=float(scores[i])) for i in order]

    async def count(self, session: AsyncSession, user_id: uuid.UUID, owner_type: OwnerType) -> int:
        total = await session.scalar(
            select(func.count()).where(
                VectorEntry.user_id == user_id, VectorEntry.owner_type == owner_type
            )
        )
        return int(total or 0)
