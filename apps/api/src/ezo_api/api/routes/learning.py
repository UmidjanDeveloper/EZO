"""Knowledge OS: libraries and learned sources (websites, GitHub repositories, packages).

Adding a source registers it and starts reading in the background; the status moves
queued → inspecting → reading → indexing → indexed / partial / failed and is returned by
every endpoint. Nothing read from a source is executed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import (
    AuditLog,
    Conversation,
    KnowledgeDocument,
    KnowledgeLibrary,
    LearnedSource,
    Message,
)
from ezo_api.knowledge.fetch import FetchError
from ezo_api.learning.analyzer import (
    CapabilityAnalyzer,
    LibraryCapabilityReport,
    SourceCapabilityAnalysis,
    cached_analysis,
)
from ezo_api.learning.base import Limits
from ezo_api.learning.service import (
    RUNNING,
    LearningError,
    LearningRunner,
    LearningService,
    get_library,
)
from ezo_api.learning.targets import parse_key
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/learning", tags=["learning"], dependencies=[Depends(rate_limit("default"))]
)


class LibraryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)


class LibraryOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    sources: int
    created_at: datetime


class SourceIn(BaseModel):
    target: str = Field(min_length=3, max_length=1_000)
    """A URL, github:owner/repo, pypi:name or npm:name."""
    kind: Literal["auto", "website", "github", "pypi", "npm"] = "auto"
    library_id: uuid.UUID | None = None
    library_name: str | None = Field(default=None, max_length=200)
    limits: Limits = Field(default_factory=Limits)


class SourceOut(BaseModel):
    id: uuid.UUID
    library_id: uuid.UUID
    kind: str
    target: str
    title: str
    status: str
    version: str | None
    license: str | None
    profile: dict[str, Any]
    limits: dict[str, Any]
    stats: dict[str, Any]
    security_flags: list[dict[str, Any]]
    error: str | None
    last_checked_at: datetime | None
    indexed_at: datetime | None
    created_at: datetime
    created: bool | None = None

    model_config = {"from_attributes": True}


class SourceDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    url: str | None
    status: str
    chunk_count: int
    size_bytes: int | None
    error: str | None


class SourceDetailOut(SourceOut):
    documents: list[SourceDocumentOut]


def _service(services: ServicesDep) -> LearningService:
    """For deleting: works even when learning is turned off (your data stays yours)."""
    assert services.learning is not None
    return services.learning.service


def _runner(services: ServicesDep) -> LearningRunner:
    if services.learning is None or not services.learning.service.enabled:
        raise HTTPException(
            503, detail={"code": "learning_off", "message": "Learning is turned off."}
        )
    return services.learning


async def _owned_library(
    session: SessionDep, user_id: uuid.UUID, library_id: uuid.UUID
) -> KnowledgeLibrary:
    library = await session.get(KnowledgeLibrary, library_id)
    if library is None or library.user_id != user_id:
        raise HTTPException(404, detail="Library not found.")
    return library


async def _owned_source(
    session: SessionDep, user_id: uuid.UUID, source_id: uuid.UUID
) -> LearnedSource:
    source = await session.get(LearnedSource, source_id)
    if source is None or source.user_id != user_id:
        raise HTTPException(404, detail="Source not found.")
    return source


@router.get("/libraries")
async def list_libraries(session: SessionDep, user: CurrentUser) -> list[LibraryOut]:
    rows = (
        await session.execute(
            select(KnowledgeLibrary, func.count(LearnedSource.id))
            .outerjoin(LearnedSource, LearnedSource.library_id == KnowledgeLibrary.id)
            .where(KnowledgeLibrary.user_id == user.id)
            .group_by(KnowledgeLibrary.id)
            .order_by(KnowledgeLibrary.created_at)
        )
    ).all()
    return [
        LibraryOut(
            id=library.id,
            name=library.name,
            description=library.description,
            sources=int(count),
            created_at=library.created_at,
        )
        for library, count in rows
    ]


@router.post("/libraries", status_code=201)
async def create_library(body: LibraryIn, session: SessionDep, user: CurrentUser) -> LibraryOut:
    name = " ".join(body.name.split())
    clash = await session.scalar(
        select(KnowledgeLibrary).where(
            KnowledgeLibrary.user_id == user.id, func.lower(KnowledgeLibrary.name) == name.lower()
        )
    )
    if clash is not None:
        raise HTTPException(
            409, detail={"code": "exists", "message": "A library with this name exists."}
        )
    library = KnowledgeLibrary(user_id=user.id, name=name, description=body.description.strip())
    session.add(library)
    await session.flush()
    audit(session, user.id, "learning.library_create", "knowledge_library", library.id, {})
    await session.commit()
    return LibraryOut(
        id=library.id,
        name=library.name,
        description=library.description,
        sources=0,
        created_at=library.created_at,
    )


@router.get("/libraries/{library_id}")
async def get_library_endpoint(
    library_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> LibraryOut:
    library = await _owned_library(session, user.id, library_id)
    count = await session.scalar(
        select(func.count(LearnedSource.id)).where(LearnedSource.library_id == library.id)
    )
    return LibraryOut(
        id=library.id,
        name=library.name,
        description=library.description,
        sources=int(count or 0),
        created_at=library.created_at,
    )


@router.delete("/libraries/{library_id}", status_code=204)
async def delete_library(
    library_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    library = await _owned_library(session, user.id, library_id)
    sources = (
        await session.scalars(select(LearnedSource).where(LearnedSource.library_id == library.id))
    ).all()
    if any(source.status in RUNNING for source in sources):
        raise HTTPException(
            409, detail={"code": "busy", "message": "A source in this library is being read."}
        )
    for source in sources:
        await _service(services).delete(session, source)
    # Conversations scoped to this library fall back to all of the user's files: say so in
    # each of them, visibly, instead of silently widening what answers draw on.
    linked = (
        await session.scalars(
            select(Conversation).where(
                Conversation.library_id == library.id, Conversation.user_id == user.id
            )
        )
    ).all()
    language = (user.preferences or {}).get("ui_language", "uz")
    notices = {
        "uz": (
            f"«{library.name}» bilim kutubxonasi o'chirildi. Bu suhbatdagi keyingi "
            "javoblar endi barcha fayllaringizdan foydalanadi."
        ),
        "en": (
            f"The knowledge library “{library.name}” was deleted. Future answers in this "
            "conversation will now use all your files."
        ),
        "ru": (
            f"Библиотека знаний «{library.name}» удалена. Следующие ответы в этом "
            "разговоре будут использовать все ваши файлы."
        ),
    }
    for conversation in linked:
        conversation.library_id = None
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=notices.get(language, notices["uz"]),
                language=language if language in notices else "uz",
                agent="knowledge_os",
                meta={"notice": "library_deleted", "library": library.name},
            )
        )
    audit(
        session,
        user.id,
        "learning.library_delete",
        "knowledge_library",
        library.id,
        {"sources": len(sources)},
    )
    await session.delete(library)
    await session.commit()
    return Response(status_code=204)


@router.post("/libraries/{library_id}/analyze", status_code=200)
async def analyze_library_capabilities(
    library_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> LibraryCapabilityReport:
    """Analyze all sources in a knowledge library to generate capability proposals (read-only)."""
    library = await _owned_library(session, user.id, library_id)
    analyzer = CapabilityAnalyzer(registered_tools=services.tools.names())
    report = await analyzer.analyze_library(session, library)
    audit(
        session,
        user.id,
        "learning.library_capability_analysis",
        "knowledge_library",
        library.id,
        {"capabilities_count": report.capabilities_count, "sources_count": report.sources_count},
    )
    await session.commit()
    return report


@router.get("/libraries/{library_id}/capabilities")
async def get_library_capabilities(
    library_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> LibraryCapabilityReport:
    """Retrieve capability analysis for a knowledge library."""
    library = await _owned_library(session, user.id, library_id)
    analyzer = CapabilityAnalyzer(registered_tools=services.tools.names())
    return await analyzer.analyze_library(session, library)


@router.get("/sources")
async def list_sources(
    session: SessionDep, user: CurrentUser, library_id: uuid.UUID | None = None
) -> list[SourceOut]:
    statement = select(LearnedSource).where(LearnedSource.user_id == user.id)
    if library_id is not None:
        statement = statement.where(LearnedSource.library_id == library_id)
    rows = (await session.scalars(statement.order_by(LearnedSource.created_at.desc()))).all()
    return [SourceOut.model_validate(row) for row in rows]


@router.post("/sources", status_code=202)
async def add_source(
    body: SourceIn,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
    response: Response,
) -> SourceOut:
    """Register a source and start reading it (202). An already registered source in the
    same library is returned as it is (200, `created: false`): use refresh to read it again."""
    runner = _runner(services)
    target = parse_key(body.kind, body.target)
    if target is None:
        raise HTTPException(
            422,
            detail={
                "code": "bad_target",
                "message": "Give a website URL, a GitHub repository, pypi:name or npm:name.",
            },
        )
    if target.kind == "website":
        try:
            await services.fetcher.check_host(target.url)
        except FetchError as exc:
            raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc
    if body.library_id is not None:
        library = await _owned_library(session, user.id, body.library_id)
    else:
        library = await get_library(session, user.id, body.library_name)
    try:
        source, created = await runner.service.add(
            session, user.id, target, library=library, limits=body.limits
        )
    except LearningError as exc:
        raise HTTPException(503, detail={"code": exc.code, "message": exc.message}) from exc
    await session.commit()
    if created:
        await runner.submit(source.id)
        await session.refresh(source)
    else:
        response.status_code = 200
    out = SourceOut.model_validate(source)
    out.created = created
    return out


@router.get("/sources/{source_id}")
async def get_source(
    source_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SourceDetailOut:
    source = await _owned_source(session, user.id, source_id)
    documents = (
        await session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source.knowledge_source_id)
            .order_by(KnowledgeDocument.created_at)
        )
    ).all()
    return SourceDetailOut(
        **SourceOut.model_validate(source).model_dump(),
        documents=[
            SourceDocumentOut(
                id=d.id,
                title=d.title,
                url=d.source_url,
                status=d.status,
                chunk_count=d.chunk_count or 0,
                size_bytes=d.size_bytes,
                error=d.error,
            )
            for d in documents
        ],
    )


@router.post("/sources/{source_id}/refresh", status_code=202)
async def refresh_source(
    source_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> SourceOut:
    runner = _runner(services)
    source = await _owned_source(session, user.id, source_id)
    if source.status in RUNNING:
        raise HTTPException(
            409, detail={"code": "busy", "message": "This source is being read already."}
        )
    source.status = "queued"
    source.error = None
    audit(session, user.id, "learning.refresh", "learned_source", source.id, {})
    await session.commit()
    await runner.submit(source.id)
    await session.refresh(source)
    return SourceOut.model_validate(source)


@router.get("/sources/{source_id}/versions")
async def source_versions(
    source_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
) -> list[dict[str, Any]]:
    """Actual run provenance only. Missing historical records are never fabricated."""
    await _owned_source(session, user.id, source_id)
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id == user.id,
                AuditLog.action == "learning.source_version",
                AuditLog.target_type == "learned_source",
                AuditLog.target_id == str(source_id),
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {"id": str(row.id), "created_at": row.created_at.isoformat(), **row.details} for row in rows
    ]


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    source = await _owned_source(session, user.id, source_id)
    if source.status in RUNNING:
        raise HTTPException(
            409,
            detail={"code": "busy", "message": "Wait until reading finishes, then delete."},
        )
    await _service(services).delete(session, source)
    await session.commit()
    return Response(status_code=204)


def _not_while_reading(source: LearnedSource) -> None:
    if source.status in RUNNING:
        raise HTTPException(
            409,
            detail={"code": "busy", "message": "The source is still being read; try again later."},
        )


@router.post("/sources/{source_id}/analyze", status_code=200)
async def analyze_source_capabilities(
    source_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> SourceCapabilityAnalysis:
    """Analyze a single learned source and formulate capability proposals."""
    source = await _owned_source(session, user.id, source_id)
    _not_while_reading(source)
    analyzer = CapabilityAnalyzer(registered_tools=services.tools.names())
    analysis = await analyzer.analyze_source(session, source)
    audit(
        session,
        user.id,
        "learning.source_capability_analysis",
        "learned_source",
        source.id,
        {"capabilities_count": len(analysis.capabilities)},
    )
    await session.commit()
    return analysis


@router.get("/sources/{source_id}/capabilities")
async def get_source_capabilities(
    source_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> SourceCapabilityAnalysis:
    """The stored analysis while it matches the content read; otherwise a fresh one, which
    a GET does not save (use POST …/analyze for that)."""
    source = await _owned_source(session, user.id, source_id)
    _not_while_reading(source)
    cached = cached_analysis(source, services.tools.names())
    if cached is not None:
        return cached
    _not_while_reading(source)
    analyzer = CapabilityAnalyzer(registered_tools=services.tools.names())
    analysis = await analyzer.analyze_source(session, source)
    await session.rollback()  # read-only request: nothing is written
    return analysis
