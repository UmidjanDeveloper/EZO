"""Official knowledge sources: what exists, what is verified, synchronization, documents.

Synchronization only runs for a source that is verified *and* enabled by the owner
(`EZO_OFFICIAL_SOURCES`). Runs are bounded (EZO_OFFICIAL_MAX_DOCUMENTS_PER_RUN) and
rate-limited; this endpoint itself is on the strict "chat" rate limit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import LegalDocument, LegalRevision, OfficialSyncRun
from ezo_api.official.base import OfficialSourceError
from ezo_api.official.registry import all_policies
from ezo_api.security.audit import audit

router = APIRouter(prefix="/api/official", tags=["official"])


class AccessReviewOut(BaseModel):
    reviewed_on: date
    official_api: str
    robots_txt: str
    terms_of_use: str
    formats: str
    rate_limits: str
    legal_basis: str
    sources: list[str]


class OfficialSourceOut(BaseModel):
    key: str
    name: str
    base_url: str
    access: str
    languages: list[str]
    can_be_enabled: bool
    enabled: bool
    supports_change_feed: bool
    min_interval_seconds: float
    notes: str
    review: AccessReviewOut


class SyncIn(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)
    language: Literal["uz", "ru"] = "uz"


class SyncRunOut(BaseModel):
    id: uuid.UUID
    connector: str
    status: str
    language: str
    requested: list[str]
    done: list[str]
    counts: dict[str, int]
    requests_made: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    resumed_from_id: uuid.UUID | None


class LegalRevisionOut(BaseModel):
    revision_number: int
    revision_label: str | None
    content_hash: str
    title: str
    status: str
    official_url: str
    retrieved_at: datetime


class LegalDocumentOut(BaseModel):
    id: uuid.UUID
    connector: str
    source_doc_id: str
    language: str
    script: str | None
    title: str
    document_number: str | None
    document_type: str | None
    authority: str | None
    adopted_on: date | None
    published_on: date | None
    effective_on: date | None
    status: str
    status_source: str
    status_verified_at: datetime | None
    official_url: str
    content_hash: str
    last_retrieved_at: datetime | None
    last_checked_at: datetime | None
    last_check_error: str | None
    duplicate_of_id: uuid.UUID | None
    knowledge_document_id: uuid.UUID | None


class LegalDocumentDetailOut(LegalDocumentOut):
    revisions: list[LegalRevisionOut]
    provenance: dict[str, object]


class LiveCheckOut(BaseModel):
    state: str
    checked_at: datetime | None
    last_verified_at: datetime | None
    message: str


def _error(exc: OfficialSourceError) -> HTTPException:
    status = {
        "unsupported_source": 400,
        "source_not_enabled": 409,
        "access_restricted": 403,
        "rate_limited": 429,
    }.get(exc.code, 502)
    return HTTPException(status, detail=exc.message)


def _run(run: OfficialSyncRun) -> SyncRunOut:
    return SyncRunOut.model_validate(run, from_attributes=True)


@router.get("/sources", dependencies=[Depends(rate_limit("default"))])
async def list_sources(user: CurrentUser, services: ServicesDep) -> list[OfficialSourceOut]:
    enabled = set(services.official.enabled)
    return [
        OfficialSourceOut(
            key=p.key,
            name=p.name,
            base_url=p.base_url,
            access=p.access,
            languages=list(p.languages),
            can_be_enabled=p.can_be_enabled,
            enabled=p.key in enabled and p.can_be_enabled,
            supports_change_feed=p.supports_change_feed,
            min_interval_seconds=max(
                p.min_interval_seconds, services.settings.official_min_interval_seconds
            ),
            notes=p.notes,
            review=AccessReviewOut(
                reviewed_on=p.review.reviewed_on,
                official_api=p.review.official_api,
                robots_txt=p.review.robots_txt,
                terms_of_use=p.review.terms_of_use,
                formats=p.review.formats,
                rate_limits=p.review.rate_limits,
                legal_basis=p.review.legal_basis,
                sources=list(p.review.sources),
            ),
        )
        for p in all_policies()
    ]


@router.post("/sources/{key}/sync", status_code=201, dependencies=[Depends(rate_limit("chat"))])
async def sync_source(
    key: str, body: SyncIn, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> SyncRunOut:
    try:
        run = await services.official.start(session, user.id, key, body.document_ids, body.language)
    except OfficialSourceError as exc:
        raise _error(exc) from exc
    audit(
        session,
        user.id,
        "official.sync",
        "official_sync_run",
        run.id,
        {"connector": key, "counts": run.counts, "status": run.status},
    )
    await session.commit()
    return _run(run)


@router.get("/runs", dependencies=[Depends(rate_limit("default"))])
async def list_runs(session: SessionDep, user: CurrentUser) -> list[SyncRunOut]:
    rows = (
        await session.scalars(
            select(OfficialSyncRun)
            .where(OfficialSyncRun.user_id == user.id)
            .order_by(OfficialSyncRun.started_at.desc())
            .limit(50)
        )
    ).all()
    return [_run(row) for row in rows]


@router.post("/runs/{run_id}/resume", status_code=201, dependencies=[Depends(rate_limit("chat"))])
async def resume_run(
    run_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> SyncRunOut:
    try:
        run = await services.official.resume(session, user.id, run_id)
    except OfficialSourceError as exc:
        raise _error(exc) from exc
    audit(session, user.id, "official.resume", "official_sync_run", run.id, {"from": str(run_id)})
    await session.commit()
    return _run(run)


@router.get("/documents", dependencies=[Depends(rate_limit("default"))])
async def list_documents(
    session: SessionDep,
    user: CurrentUser,
    connector: str | None = None,
    status: str | None = None,
    include_duplicates: bool = Query(default=False),
) -> list[LegalDocumentOut]:
    statement = select(LegalDocument).where(LegalDocument.user_id == user.id)
    if connector:
        statement = statement.where(LegalDocument.connector == connector)
    if status:
        statement = statement.where(LegalDocument.status == status)
    if not include_duplicates:
        statement = statement.where(LegalDocument.duplicate_of_id.is_(None))
    rows = (
        await session.scalars(statement.order_by(LegalDocument.updated_at.desc()).limit(500))
    ).all()
    return [LegalDocumentOut.model_validate(row, from_attributes=True) for row in rows]


async def _owned(session: SessionDep, user_id: uuid.UUID, document_id: uuid.UUID) -> LegalDocument:
    row = await session.get(LegalDocument, document_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, detail="Official document not found.")
    return row


@router.get("/documents/{document_id}", dependencies=[Depends(rate_limit("default"))])
async def get_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> LegalDocumentDetailOut:
    row = await _owned(session, user.id, document_id)
    revisions = (
        await session.scalars(
            select(LegalRevision)
            .where(LegalRevision.legal_document_id == row.id)
            .order_by(LegalRevision.revision_number.desc())
        )
    ).all()
    base = LegalDocumentOut.model_validate(row, from_attributes=True)
    return LegalDocumentDetailOut(
        **base.model_dump(),
        revisions=[LegalRevisionOut.model_validate(r, from_attributes=True) for r in revisions],
        provenance=dict(row.provenance or {}),
    )


@router.post("/documents/{document_id}/verify", dependencies=[Depends(rate_limit("chat"))])
async def verify_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> LiveCheckOut:
    row = await _owned(session, user.id, document_id)
    check = await services.official.verify_live(session, row)
    audit(session, user.id, "official.verify", "legal_document", row.id, {"state": check.state})
    await session.commit()
    return LiveCheckOut(
        state=check.state,
        checked_at=check.checked_at,
        last_verified_at=check.last_verified_at,
        message=check.message,
    )
