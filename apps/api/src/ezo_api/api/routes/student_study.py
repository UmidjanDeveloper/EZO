"""Additive Student practice API, independent of frontend implementation."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.api.routes.document_jobs import _call
from ezo_api.db.base import utcnow
from ezo_api.db.models import KnowledgeDocument, StudyCard, StudyReview
from ezo_api.security.audit import audit
from ezo_api.student.study import (
    CardIn,
    ReviewIn,
    active_filters,
    card_out,
    create_card,
    review_card,
    scope,
)
from ezo_api.student.synthesis import SynthesisIn, context, llama_nodes, synthesize

router = APIRouter(
    prefix="/api/student", tags=["student-study"], dependencies=[Depends(rate_limit("default"))]
)


@router.post("/synthesize", dependencies=[Depends(rate_limit("chat"))])
async def synthesis(
    body: SynthesisIn,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, object]:
    return await _call(synthesize(services, session, user.id, body))


@router.post("/context", dependencies=[Depends(rate_limit("chat"))])
async def shared_context(
    body: SynthesisIn,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, object]:
    sources = await _call(context(services, session, user.id, body))
    return {
        "nodes": llama_nodes(sources),
        "trust": "untrusted_source_data",
        "action_authority": "none",
        "purpose": "owner_requested_read_only_context",
    }


@router.post("/cards", status_code=201)
async def add_card(body: CardIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    return await _call(create_card(session, user.id, body))


@router.get("/cards")
async def cards(
    user: CurrentUser,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    due_only: bool = False,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(30, ge=1, le=100),
) -> list[dict[str, Any]]:
    await _call(scope(session, user.id, project_id))
    statement = (
        select(StudyCard)
        .join(KnowledgeDocument, KnowledgeDocument.id == StudyCard.document_id)
        .where(*active_filters(user.id, project_id))
    )
    if due_only:
        statement = statement.where(StudyCard.due_at <= utcnow())
    rows = (
        await session.scalars(
            statement.order_by(StudyCard.due_at, StudyCard.id).offset(offset).limit(limit)
        )
    ).all()
    return [card_out(card) for card in rows]


@router.post("/cards/{card_id}/review")
async def review(
    card_id: uuid.UUID,
    body: ReviewIn,
    user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    return await _call(review_card(session, user.id, card_id, body))


@router.get("/progress")
async def progress(
    user: CurrentUser,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    await _call(scope(session, user.id, project_id))
    active = (
        select(StudyCard.id)
        .join(KnowledgeDocument, KnowledgeDocument.id == StudyCard.document_id)
        .where(*active_filters(user.id, project_id))
    )
    total = await session.scalar(select(func.count()).select_from(active.subquery()))
    due = await session.scalar(
        select(func.count()).select_from(active.where(StudyCard.due_at <= utcnow()).subquery())
    )
    reviews, reviewed = (
        await session.execute(
            select(
                func.count(StudyReview.id), func.count(func.distinct(StudyReview.card_id))
            ).where(StudyReview.card_id.in_(active))
        )
    ).one()
    return {
        "active_cards": total,
        "due_cards": due,
        "review_events": reviews,
        "reviewed_cards": reviewed,
        "assessment": "self_reported_recall",
        "scope": "current_source_revisions",
    }


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(
    card_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    confirm: bool = False,
) -> Response:
    await _call(scope(session, user.id, project_id))
    card = await session.scalar(
        select(StudyCard).where(
            StudyCard.id == card_id,
            StudyCard.user_id == user.id,
            StudyCard.project_id.is_not_distinct_from(project_id),
        )
    )
    if card is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Card not found."})
    elif not confirm:
        raise HTTPException(
            409,
            detail={
                "code": "confirmation_required",
                "message": "Confirm deletion of this card and history.",
            },
        )
    else:
        audit(session, user.id, "student.card_delete", "study_card", card.id, {})
        await session.delete(card)
        await session.commit()
        return Response(status_code=204)
