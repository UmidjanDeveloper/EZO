"""Explicit bounded semantic-index batches using K1's existing vector providers."""

import asyncio
import uuid

from sqlalchemy import select

from ezo_api.db.models import KnowledgeChunk
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.knowledge.vectorstores.base import VectorRecord
from ezo_api.services import Services
from ezo_api.student.ingestion import StudentIngestion


async def index_batch(
    services: Services,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    document_id: uuid.UUID,
    offset: int,
) -> dict[str, object]:
    jobs = StudentIngestion(services.db)
    async with jobs._transaction(write=False) as session:
        doc = await jobs._document(session, user_id, project_id, document_id)
        revision_id = doc.current_revision_id
        if revision_id is None or doc.status not in ("indexed", "partial"):
            raise JobError("source_not_ready", "The document is not indexed.")
        chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.document_id == document_id,
                        KnowledgeChunk.revision_id == revision_id,
                        KnowledgeChunk.user_id == user_id,
                    )
                    .order_by(KnowledgeChunk.chunk_index)
                    .offset(offset)
                    .limit(32)
                )
            ).all()
        )
    if not services.embeddings.available:
        raise JobError("provider_unavailable", "No embedding provider is configured.", 503)
    if not chunks:
        return {"indexed": 0, "next_offset": None, "revision_id": str(revision_id)}
    try:
        async with asyncio.timeout(40):
            vectors = await services.embeddings.embed_documents([c.text for c in chunks])
    except Exception as exc:
        raise JobError("provider_unavailable", "Embedding request failed.", 503) from exc
    async with jobs._transaction() as session:
        doc = await jobs._document(session, user_id, project_id, document_id, lock=True)
        if doc.current_revision_id != revision_id:
            raise JobError("revision_conflict", "The source changed during indexing.")
        store = await services.vectors.get(session)
        await store.upsert(
            session,
            [
                VectorRecord(
                    owner_type="chunk",
                    owner_id=c.id,
                    user_id=user_id,
                    model=services.embeddings.model_key or "",
                    vector=v,
                    document_id=document_id,
                    project_id=project_id,
                )
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )
        return {
            "indexed": len(chunks),
            "next_offset": offset + len(chunks) if offset + len(chunks) < doc.chunk_count else None,
            "revision_id": str(revision_id),
        }
