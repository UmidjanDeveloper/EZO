"""Lexical (keyword) search over current-revision chunks.

PostgreSQL: built-in full-text search ('simple' configuration — works for
Uzbek, English and Russian without language-specific stemming).
SQLite: BM25 computed in Python over the user's chunks.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, bindparam, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import KnowledgeChunk, KnowledgeDocument
from ezo_api.memory.scoring import stem_tokens, stems

SEARCHABLE_STATUSES = ("indexed", "partial")
MAX_LOCAL_SCAN = 20_000
_SAFE_TERM = re.compile(r"^\w+$", re.UNICODE)


@dataclass(frozen=True, slots=True)
class KeywordHit:
    chunk_id: uuid.UUID
    score: float
    coverage: float
    """Share of distinct query terms found in the chunk (0..1)."""


def current_chunks_query(
    user_id: uuid.UUID,
    project_scope: uuid.UUID | None,
    document_ids: frozenset[uuid.UUID] | None = None,
) -> Select:  # type: ignore[type-arg]
    statement = (
        select(KnowledgeChunk.id, KnowledgeChunk.text)
        .join(
            KnowledgeDocument,
            and_(
                KnowledgeDocument.id == KnowledgeChunk.document_id,
                KnowledgeDocument.current_revision_id == KnowledgeChunk.revision_id,
            ),
        )
        .where(
            KnowledgeChunk.user_id == user_id,
            KnowledgeDocument.status.in_(SEARCHABLE_STATUSES),
            or_(
                KnowledgeDocument.project_id.is_(None),
                KnowledgeDocument.project_id == project_scope,
            ),
        )
    )
    if document_ids is not None:
        statement = statement.where(KnowledgeDocument.id.in_(document_ids))
    return statement


async def has_searchable_documents(
    session: AsyncSession, user_id: uuid.UUID, project_scope: uuid.UUID | None
) -> bool:
    """Cheap check so ordinary chat skips retrieval when there is nothing to search."""
    found = await session.scalar(
        select(KnowledgeDocument.id)
        .where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status.in_(SEARCHABLE_STATUSES),
            or_(
                KnowledgeDocument.project_id.is_(None),
                KnowledgeDocument.project_id == project_scope,
            ),
        )
        .limit(1)
    )
    return found is not None


def coverage(query_stems: set[str], chunk_text: str) -> float:
    if not query_stems:
        return 0.0
    return len(query_stems & stems(chunk_text)) / len(query_stems)


async def keyword_search(
    session: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    project_scope: uuid.UUID | None,
    limit: int = 20,
    document_ids: frozenset[uuid.UUID] | None = None,
) -> list[KeywordHit]:
    query_stems = stems(query)
    if not query_stems:
        return []
    base = current_chunks_query(user_id, project_scope, document_ids)
    if session.get_bind().dialect.name == "postgresql":
        return await _postgres(session, base, query_stems, limit)
    return await _bm25(session, base, query_stems, limit)


async def _postgres(
    session: AsyncSession,
    base: Select,  # type: ignore[type-arg]
    query_stems: set[str],
    limit: int,
) -> list[KeywordHit]:
    terms = [term for term in sorted(query_stems) if _SAFE_TERM.match(term)]
    if not terms:
        return []
    # Prefix matching (term:*) approximates stemming for Uzbek/Russian suffixes.
    config: ColumnElement[Any] = literal_column("'simple'::regconfig")
    vector = func.to_tsvector(config, KnowledgeChunk.text)
    query = func.to_tsquery(config, bindparam("q"))
    rank = func.ts_rank(vector, query).label("rank")
    statement = base.add_columns(rank).where(vector.op("@@")(query)).order_by(rank.desc())
    rows = (
        await session.execute(statement.limit(limit), {"q": " | ".join(f"{t}:*" for t in terms)})
    ).all()
    return [
        KeywordHit(chunk_id=row[0], score=float(row[2]), coverage=coverage(query_stems, row[1]))
        for row in rows
    ]


async def _bm25(
    session: AsyncSession,
    base: Select,  # type: ignore[type-arg]
    query_stems: set[str],
    limit: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[KeywordHit]:
    rows = (await session.execute(base.limit(MAX_LOCAL_SCAN))).all()
    if not rows:
        return []
    documents: list[tuple[uuid.UUID, str, Counter[str]]] = []
    df: Counter[str] = Counter()
    for chunk_id, chunk_text in rows:
        counts = Counter(stem_tokens(chunk_text))
        documents.append((chunk_id, chunk_text, counts))
        df.update(set(counts) & query_stems)
    n = len(documents)
    avg_len = sum(sum(c.values()) for _, _, c in documents) / n or 1.0
    hits: list[KeywordHit] = []
    for chunk_id, chunk_text, counts in documents:
        length = sum(counts.values()) or 1
        score = 0.0
        for term in query_stems:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg_len))
        if score > 0:
            hits.append(KeywordHit(chunk_id, score, coverage(query_stems, chunk_text)))
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]
