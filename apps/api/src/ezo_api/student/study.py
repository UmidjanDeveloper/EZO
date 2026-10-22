"""Durable explicit study actions; source text never authorizes tools or execution."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    Project,
    StudyCard,
    StudyReview,
)
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.security.audit import audit
from ezo_api.student.provenance import chunk_offsets


class CardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: uuid.UUID
    revision_id: uuid.UUID
    chunk_id: uuid.UUID
    project_id: uuid.UUID | None = None
    front: str = Field(min_length=1, max_length=600)
    back: str = Field(min_length=1, max_length=2000)
    quote_start: int = Field(ge=0, le=2_000_000)
    quote_end: int = Field(ge=1, le=2_000_000)

    @field_validator("front", "back")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter nonblank text.")
        return value


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID | None = None
    event_id: uuid.UUID
    expected_version: int = Field(ge=0, le=10000)
    rating: Literal["again", "hard", "good", "easy"]


def card_out(card: StudyCard) -> dict[str, Any]:
    return {
        "id": str(card.id),
        "document_id": str(card.document_id),
        "revision_id": str(card.revision_id),
        "chunk_id": str(card.chunk_id),
        "project_id": str(card.project_id) if card.project_id else None,
        "front": card.front,
        "back": card.back,
        "quote": card.quote,
        "quote_start": card.quote_start,
        "quote_end": card.quote_end,
        "offset_unit": "unicode_codepoints",
        "due_at": card.due_at.isoformat(),
        "version": card.version,
        "interval_days": card.interval_days,
        "schedule": "bounded-recall-v1",
        "assessment": "self_reported_recall",
    }


async def scope(session: AsyncSession, user: uuid.UUID, project: uuid.UUID | None) -> None:
    if (
        project is not None
        and await session.scalar(
            select(Project.id).where(Project.id == project, Project.user_id == user)
        )
        is None
    ):
        raise JobError("not_found", "Project not found.", 404)


def active_filters(user: uuid.UUID, project: uuid.UUID | None) -> list[Any]:
    return [
        StudyCard.user_id == user,
        StudyCard.project_id.is_not_distinct_from(project),
        KnowledgeDocument.user_id == user,
        KnowledgeDocument.project_id.is_not_distinct_from(project),
        KnowledgeDocument.current_revision_id == StudyCard.revision_id,
        KnowledgeDocument.status.in_(("indexed", "partial")),
    ]


async def create_card(session: AsyncSession, user: uuid.UUID, body: CardIn) -> dict[str, Any]:
    await scope(session, user, body.project_id)
    doc = await session.scalar(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == body.document_id,
            KnowledgeDocument.user_id == user,
            KnowledgeDocument.project_id.is_not_distinct_from(body.project_id),
        )
        .with_for_update()
    )
    if doc is None:
        raise JobError("not_found", "Document not found.", 404)
    if doc.current_revision_id != body.revision_id or doc.status not in ("indexed", "partial"):
        raise JobError("revision_conflict", "Use the current indexed revision.")
    chunk = await session.scalar(
        select(KnowledgeChunk).where(
            KnowledgeChunk.id == body.chunk_id,
            KnowledgeChunk.user_id == user,
            KnowledgeChunk.document_id == doc.id,
            KnowledgeChunk.revision_id == body.revision_id,
        )
    )
    size = body.quote_end - body.quote_start
    if chunk is None or not 1 <= size <= 2000:
        raise JobError(
            "invalid_citation", "Select an exact source quote of 1..2000 characters.", 422
        )
    offsets = await chunk_offsets(session, chunk)
    if offsets is None:
        raise JobError("invalid_citation", "Source chunk offsets are ambiguous or invalid.", 422)
    start, end = offsets
    if not (start <= body.quote_start < body.quote_end <= end):
        raise JobError(
            "invalid_citation", "Select a quote within an offset-indexed source chunk.", 422
        )
    quote = await session.scalar(
        select(func.substr(DocumentRevision.raw_text, body.quote_start + 1, size)).where(
            DocumentRevision.id == body.revision_id, DocumentRevision.document_id == doc.id
        )
    )
    if (
        quote is None
        or len(quote) != size
        or quote != chunk.text[body.quote_start - start : body.quote_end - start]
    ):
        raise JobError("invalid_citation", "Source offsets could not be verified.", 422)
    count = await session.scalar(
        select(func.count()).select_from(StudyCard).where(StudyCard.document_id == doc.id)
    )
    if (count or 0) >= 250:
        raise JobError("card_limit", "Maximum 250 cards per document.")
    card = StudyCard(
        user_id=user,
        project_id=body.project_id,
        document_id=doc.id,
        revision_id=body.revision_id,
        chunk_id=chunk.id,
        front=body.front,
        back=body.back,
        quote=quote,
        quote_start=body.quote_start,
        quote_end=body.quote_end,
    )
    session.add(card)
    await session.flush()
    audit(session, user, "student.card_create", "study_card", card.id, {})
    await session.commit()
    return card_out(card)


async def review_card(
    session: AsyncSession, user: uuid.UUID, card_id: uuid.UUID, body: ReviewIn
) -> dict[str, Any]:
    await scope(session, user, body.project_id)
    card = await session.scalar(
        select(StudyCard).where(
            StudyCard.id == card_id,
            StudyCard.user_id == user,
            StudyCard.project_id.is_not_distinct_from(body.project_id),
        )
    )
    if card is None:
        raise JobError("not_found", "Card not found.", 404)

    async def replay() -> dict[str, Any] | None:
        prior = await session.scalar(
            select(StudyReview).where(
                StudyReview.card_id == card.id, StudyReview.event_id == body.event_id
            )
        )
        if prior is None:
            return None
        if prior.expected_version != body.expected_version or prior.rating != body.rating:
            raise JobError("idempotency_conflict", "Review event ID was already used.")
        return prior.result

    previous = await replay()
    if previous is not None:
        return previous
    active = await session.scalar(
        select(KnowledgeDocument.id)
        .where(
            KnowledgeDocument.id == card.document_id,
            KnowledgeDocument.current_revision_id == card.revision_id,
            KnowledgeDocument.user_id == user,
            KnowledgeDocument.project_id.is_not_distinct_from(body.project_id),
            KnowledgeDocument.status.in_(("indexed", "partial")),
        )
        .with_for_update()
    )
    if active is None:
        raise JobError("revision_conflict", "The source changed or is no longer available.")
    await session.refresh(card)
    previous = await replay()
    if previous is not None:
        return previous
    if card.version != body.expected_version:
        raise JobError("review_conflict", "The card was reviewed elsewhere. Reload it.")
    if card.version >= 10000:
        raise JobError("review_limit", "Card review budget exhausted.")
    days = {
        "again": 0,
        "hard": max(1, card.interval_days),
        "good": max(1, card.interval_days * 2),
        "easy": max(4, card.interval_days * 3),
    }[body.rating]
    days = min(days, 365)
    now = utcnow()
    due = now + (timedelta(days=days) if days else timedelta(minutes=10))
    changed = await session.execute(
        update(StudyCard)
        .where(StudyCard.id == card.id, StudyCard.version == body.expected_version)
        .values(version=body.expected_version + 1, interval_days=days, due_at=due)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:  # type: ignore[attr-defined]
        previous = await replay()
        if previous is not None:
            return previous
        raise JobError("review_conflict", "The card was reviewed elsewhere. Reload it.")
    result = {
        "card_id": str(card.id),
        "event_id": str(body.event_id),
        "version": body.expected_version + 1,
        "interval_days": days,
        "due_at": due.isoformat(),
        "rating": body.rating,
        "schedule": "bounded-recall-v1",
        "assessment": "self_reported_recall",
    }
    session.add(
        StudyReview(
            card_id=card.id,
            event_id=body.event_id,
            expected_version=body.expected_version,
            rating=body.rating,
            result=result,
        )
    )
    audit(
        session,
        user,
        "student.card_review",
        "study_card",
        card.id,
        {"event_id": str(body.event_id), "version": body.expected_version + 1},
    )
    await session.commit()
    return result
