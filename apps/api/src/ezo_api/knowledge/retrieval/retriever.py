"""Hybrid retrieval: query analysis → filters → keyword + vector search →
reciprocal-rank fusion → rerank → context selection → source packaging."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import DocumentRevision, KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from ezo_api.knowledge.embeddings.service import EmbeddingError, EmbeddingService
from ezo_api.knowledge.retrieval.keyword import SEARCHABLE_STATUSES, keyword_search
from ezo_api.knowledge.retrieval.rerank import PassthroughReranker, Reranker
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.knowledge.vectorstores import VectorFilter, VectorStoreResolver
from ezo_api.memory.scoring import stems

logger = logging.getLogger(__name__)

RRF_K = 60
CANDIDATES = 20
MAX_PER_DOCUMENT = 3
CONTEXT_CHAR_BUDGET = 9_000

# Relevance gates. "strict" is used when EZO searches on its own initiative
# (ordinary chat); explicit research/document questions use "relaxed".
STRICT_VECTOR = 0.40
STRICT_COVERAGE = 0.5
RELAXED_VECTOR = 0.20


@dataclass(slots=True)
class _Candidate:
    chunk_id: uuid.UUID
    fused: float = 0.0
    vector_score: float | None = None
    keyword_score: float | None = None
    coverage: float = 0.0


@dataclass(slots=True)
class RetrievalResult:
    sources: list[SourceRef]
    mode: str  # hybrid | keyword | vector | none
    diagnostics: dict[str, Any] = field(default_factory=dict)


class Retriever:
    def __init__(
        self,
        embeddings: EmbeddingService,
        vectors: VectorStoreResolver,
        reranker: Reranker | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.vectors = vectors
        self.reranker: Reranker = reranker or PassthroughReranker()

    async def retrieve(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        query: str,
        project_scope: uuid.UUID | None = None,
        limit: int = 6,
        strict: bool = False,
        document_ids: frozenset[uuid.UUID] | None = None,
    ) -> RetrievalResult:
        query = query.strip()
        diagnostics: dict[str, Any] = {"query_terms": len(stems(query))}
        if not query:
            return RetrievalResult([], "none", diagnostics)

        candidates: dict[uuid.UUID, _Candidate] = {}

        # Lexical search.
        keyword_hits = await keyword_search(
            session, query, user_id, project_scope, CANDIDATES, document_ids
        )
        for rank, hit in enumerate(keyword_hits):
            candidate = candidates.setdefault(hit.chunk_id, _Candidate(hit.chunk_id))
            candidate.fused += 1 / (RRF_K + rank + 1)
            candidate.keyword_score = hit.score
            candidate.coverage = hit.coverage
        diagnostics["keyword_hits"] = len(keyword_hits)

        # Vector search (only with an embedding model; never mixes models).
        vector_used = False
        if self.embeddings.available and self.embeddings.model_key:
            try:
                vector = await self.embeddings.embed_query(query)
                store = await self.vectors.get(session)
                hits = await store.search(
                    session,
                    vector,
                    VectorFilter(
                        user_id=user_id,
                        owner_type="chunk",
                        model=self.embeddings.model_key,
                        project_scope=project_scope,
                        document_ids=document_ids,
                    ),
                    CANDIDATES,
                )
                vector_used = True
                diagnostics["vector_hits"] = len(hits)
                for rank, vector_hit in enumerate(hits):
                    owner = vector_hit.owner_id
                    candidate = candidates.setdefault(owner, _Candidate(owner))
                    candidate.fused += 1 / (RRF_K + rank + 1)
                    candidate.vector_score = vector_hit.score
            except EmbeddingError as exc:
                diagnostics["vector_error"] = exc.message

        mode = (
            "hybrid"
            if vector_used and keyword_hits
            else "vector"
            if vector_used
            else "keyword"
            if keyword_hits
            else "none"
        )
        min_vector = STRICT_VECTOR if strict else RELAXED_VECTOR
        relevant = [
            c
            for c in candidates.values()
            if (c.vector_score is not None and c.vector_score >= min_vector)
            or (c.keyword_score is not None and c.coverage >= (STRICT_COVERAGE if strict else 0.01))
        ]
        relevant.sort(key=lambda c: c.fused, reverse=True)
        diagnostics["relevant"] = len(relevant)
        if not relevant:
            return RetrievalResult([], mode, diagnostics)

        rows = await self._load(session, [c.chunk_id for c in relevant])
        ordered = [c for c in relevant if c.chunk_id in rows]
        ordered = await self.reranker.rerank(
            query, ordered, [rows[c.chunk_id][0].text for c in ordered]
        )

        # Context selection: per-document cap, character budget, no duplicates.
        sources: list[SourceRef] = []
        per_document: dict[uuid.UUID, int] = {}
        seen_text: set[str] = set()
        budget = CONTEXT_CHAR_BUDGET
        for candidate in ordered:
            chunk, document, revision, source = rows[candidate.chunk_id]
            if per_document.get(document.id, 0) >= MAX_PER_DOCUMENT:
                continue
            key = chunk.text.strip()[:200]
            if key in seen_text or len(chunk.text) > budget:
                continue
            seen_text.add(key)
            per_document[document.id] = per_document.get(document.id, 0) + 1
            budget -= len(chunk.text)
            sources.append(_to_source(chunk, document, revision, source, candidate))
            if len(sources) >= limit:
                break
        return RetrievalResult(sources, mode, diagnostics)

    async def _load(
        self, session: AsyncSession, chunk_ids: list[uuid.UUID]
    ) -> dict[
        uuid.UUID, tuple[KnowledgeChunk, KnowledgeDocument, DocumentRevision, KnowledgeSource]
    ]:
        """Load chunks that still belong to the current revision of a searchable document."""
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, DocumentRevision, KnowledgeSource)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .join(DocumentRevision, DocumentRevision.id == KnowledgeChunk.revision_id)
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeDocument.source_id)
            .where(
                KnowledgeChunk.id.in_(chunk_ids),
                KnowledgeDocument.current_revision_id == KnowledgeChunk.revision_id,
                KnowledgeDocument.status.in_(SEARCHABLE_STATUSES),
            )
        )
        result = await session.execute(statement)
        return {row[0].id: (row[0], row[1], row[2], row[3]) for row in result.all()}


def _to_source(
    chunk: KnowledgeChunk,
    document: KnowledgeDocument,
    revision: DocumentRevision,
    source: KnowledgeSource,
    candidate: _Candidate,
) -> SourceRef:
    meta = chunk.meta or {}
    doc_meta = document.meta or {}
    published = doc_meta.get("date")
    indexed = document.indexed_at or document.updated_at
    return SourceRef(
        kind="web_page" if document.source_url else "file",
        title=document.title,
        excerpt=chunk.text,
        source_name=(
            str(doc_meta.get("sitename") or doc_meta.get("hostname") or source.name)
            if document.source_url
            else f"{source.name} · {document.filename or document.title}"
        ),
        url=document.source_url,
        date=str(published) if published else indexed.date().isoformat(),
        document_id=document.id,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        page_start=meta.get("page_start"),
        page_end=meta.get("page_end"),
        heading=meta.get("heading"),
        score=round(candidate.fused, 5),
        reliability=0.8,
        extra={
            "vector_score": candidate.vector_score,
            "keyword_coverage": round(candidate.coverage, 2),
        },
    )
