"""Knowledge base endpoints: upload files, add web pages, inspect, reindex, delete, search."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    OcrPage,
    Project,
)
from ezo_api.documents.isolation import native_fixtures_allowed
from ezo_api.knowledge.fetch import FetchError
from ezo_api.knowledge.uploads import ALLOWED_EXTENSIONS, UploadRejectedError
from ezo_api.schemas.knowledge import (
    ChunkPreviewOut,
    KnowledgeDocumentDetailOut,
    KnowledgeDocumentOut,
    KnowledgeSourceOut,
    KnowledgeStatusOut,
    RevisionOut,
    SearchIn,
    SearchOut,
    UploadOut,
    UrlIn,
)
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/knowledge", tags=["knowledge"], dependencies=[Depends(rate_limit("default"))]
)

_PUBLIC_META = (
    "category",
    "pages",
    "sheets",
    "rows",
    "truncated",
    "chars",
    "embedding_model",
    "author",
    "date",
    "sitename",
    "final_url",
    "ocr",
    "refresh_observation",
)


def _rejected(exc: UploadRejectedError | FetchError) -> HTTPException:
    return HTTPException(422, detail={"code": exc.code, "message": exc.message})


async def _check_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID | None
) -> None:
    if project_id is not None:
        project = await session.get(Project, project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(404, detail="Project not found.")


async def _document_out(session: AsyncSession, document: KnowledgeDocument) -> KnowledgeDocumentOut:
    source = await session.get(KnowledgeSource, document.source_id)
    revision_number = None
    if document.current_revision_id:
        revision_number = await session.scalar(
            select(DocumentRevision.revision_number).where(
                DocumentRevision.id == document.current_revision_id
            )
        )
    meta = document.meta or {}
    return KnowledgeDocumentOut(
        id=document.id,
        title=document.title,
        filename=document.filename,
        source_id=document.source_id,
        source_type=source.source_type if source else "upload",
        source_name=source.name if source else "",
        project_id=document.project_id,
        mime_type=document.mime_type,
        source_url=document.source_url,
        size_bytes=document.size_bytes,
        language=document.language,
        status=document.status,
        error=document.error,
        chunk_count=document.chunk_count,
        current_revision=revision_number,
        created_at=document.created_at,
        updated_at=document.updated_at,
        indexed_at=document.indexed_at,
        metadata={k: meta[k] for k in _PUBLIC_META if k in meta},
    )


async def _owned(
    session: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID
) -> KnowledgeDocument:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or document.user_id != user_id:
        raise HTTPException(404, detail="Document not found.")
    return document


@router.get("/status")
async def knowledge_status(
    session: SessionDep, user: CurrentUser, services: ServicesDep
) -> KnowledgeStatusOut:
    store = await services.vectors.get(session)
    rows = (
        await session.execute(
            select(KnowledgeDocument.status, func.count())
            .where(KnowledgeDocument.user_id == user.id)
            .group_by(KnowledgeDocument.status)
        )
    ).all()
    chunks = await session.scalar(
        select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.user_id == user.id)
    )
    by_status = {status: int(count) for status, count in rows}
    return KnowledgeStatusOut(
        vector_store=store.name,
        embedding_model=services.embeddings.model_key,
        semantic_search=services.embeddings.available,
        web_search=services.web_search.name if services.web_search else None,
        max_upload_mb=services.settings.max_upload_mb,
        allowed_extensions=sorted(
            ALLOWED_EXTENSIONS
            if native_fixtures_allowed()
            else [".txt", ".md", ".markdown", ".csv"]
        ),
        documents=sum(by_status.values()),
        chunks=int(chunks or 0),
        by_status=by_status,
    )


@router.get("/documents")
async def list_documents(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    library_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    include_learned: bool = False,
) -> list[KnowledgeDocumentOut]:
    """The user's files and pages. Pages of learned sources (Knowledge OS) are listed under
    their source (/api/learning/sources/{id}) unless `include_learned` is set."""
    statement = select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id)
    if library_id is not None:
        from ezo_api.learning.service import resolve_library_documents

        _lib, doc_ids = await resolve_library_documents(
            session, user_id=user.id, library_id=library_id
        )
        if not doc_ids:
            return []
        statement = statement.where(KnowledgeDocument.id.in_(doc_ids))
    elif not include_learned:
        learned = select(KnowledgeSource.id).where(
            KnowledgeSource.user_id == user.id, KnowledgeSource.source_type == "learned"
        )
        statement = statement.where(KnowledgeDocument.source_id.not_in(learned))
    if project_id is not None:
        statement = statement.where(KnowledgeDocument.project_id == project_id)
    statement = statement.order_by(KnowledgeDocument.updated_at.desc()).limit(limit)
    documents = (await session.scalars(statement)).all()
    return [await _document_out(session, d) for d in documents]


@router.post("/documents", status_code=201)
async def upload_document(
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
    response: Response,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
    project_id: uuid.UUID | None = Form(default=None),  # noqa: B008
) -> UploadOut:
    await _check_project(session, user.id, project_id)
    limit = services.settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            413,
            detail={
                "code": "too_large",
                "message": f"The file is larger than {services.settings.max_upload_mb} MB.",
            },
        )
    try:
        result = await services.knowledge.add_upload(
            session, user.id, file.filename or "file", data, project_id
        )
    except UploadRejectedError as exc:
        raise _rejected(exc) from exc
    if result.duplicate:
        response.status_code = 200
    else:
        audit(
            session,
            user.id,
            "knowledge.upload",
            "document",
            result.document.id,
            {"filename": result.document.filename, "revision": result.new_revision},
        )
    await session.commit()
    if not result.duplicate:
        await services.ingestion.submit(result.document.id)
        await session.refresh(result.document)
    return UploadOut(
        document=await _document_out(session, result.document),
        duplicate=result.duplicate,
        new_revision=result.new_revision,
    )


@router.post("/urls", status_code=201)
async def add_url(
    body: UrlIn, session: SessionDep, user: CurrentUser, services: ServicesDep, response: Response
) -> UploadOut:
    await _check_project(session, user.id, body.project_id)
    try:
        result = await services.knowledge.add_url(
            session, user.id, body.url.strip(), body.project_id
        )
    except (UploadRejectedError, FetchError) as exc:
        raise _rejected(exc) from exc
    if result.duplicate:
        response.status_code = 200
    else:
        audit(
            session, user.id, "knowledge.add_url", "document", result.document.id, {"url": body.url}
        )
    await session.commit()
    if not result.duplicate:
        await services.ingestion.submit(result.document.id)
        await session.refresh(result.document)
    return UploadOut(
        document=await _document_out(session, result.document),
        duplicate=result.duplicate,
        new_revision=result.new_revision,
    )


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> KnowledgeDocumentDetailOut:
    document = await _owned(session, user.id, document_id)
    revisions = (
        await session.scalars(
            select(DocumentRevision)
            .where(DocumentRevision.document_id == document.id)
            .order_by(DocumentRevision.revision_number.desc())
        )
    ).all()
    chunks = (
        (
            await session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.revision_id == document.current_revision_id)
                .order_by(KnowledgeChunk.chunk_index)
                .limit(5)
            )
        ).all()
        if document.current_revision_id
        else []
    )
    base = await _document_out(session, document)
    return KnowledgeDocumentDetailOut(
        **base.model_dump(),
        revisions=[
            RevisionOut(
                id=r.id,
                revision_number=r.revision_number,
                content_hash=r.content_hash,
                chars=len(r.raw_text),
                created_at=r.created_at,
                current=r.id == document.current_revision_id,
            )
            for r in revisions
        ],
        chunks_preview=[
            ChunkPreviewOut(chunk_index=c.chunk_index, text=c.text[:400], metadata=c.meta or {})
            for c in chunks
        ],
    )


@router.post("/documents/{document_id}/reindex")
async def reindex_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> KnowledgeDocumentOut:
    document = await _owned(session, user.id, document_id)
    if (document.meta or {}).get("student") is True:
        raise HTTPException(
            409,
            detail={
                "code": "student_managed",
                "message": "Use Student job retry for this document.",
            },
        )
    if document.status in ("queued", "processing"):
        raise HTTPException(409, detail="The document is already being processed.")
    document.status = "queued"
    document.error = None
    audit(session, user.id, "knowledge.reindex", "document", document.id)
    await session.commit()
    await services.ingestion.submit(document.id)
    await session.refresh(document)
    return await _document_out(session, document)


@router.get("/documents/{document_id}/ocr")
async def get_document_ocr(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[dict[str, Any]]:
    """What OCR read on each page, with line boxes, language packs, the engine's own
    confidence (0-100, not a calibrated accuracy), preprocessing and warnings."""
    document = await _owned(session, user.id, document_id)
    rows = (
        await session.scalars(
            select(OcrPage)
            .where(OcrPage.document_id == document.id, OcrPage.user_id == user.id)
            .order_by(OcrPage.page_number)
        )
    ).all()
    return [
        {
            "page": r.page_number,
            "text": r.text,
            "lines": r.lines,
            "width": r.width,
            "height": r.height,
            "dpi": r.dpi,
            "languages": r.languages,
            "script": r.script,
            "detected_language": r.detected_language,
            "method": r.method,
            "engine_version": r.engine_version,
            "confidence": r.confidence,
            "rotation": r.rotation,
            "deskew_angle": r.deskew_angle,
            "current": r.source_content_hash == document.content_hash,
            "warnings": r.warnings,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> Response:
    document = await _owned(session, user.id, document_id)
    audit(session, user.id, "knowledge.delete", "document", document.id, {"title": document.title})
    await services.knowledge.delete_document(session, document)
    await session.commit()
    return Response(status_code=204)


@router.get("/sources")
async def list_sources(session: SessionDep, user: CurrentUser) -> list[KnowledgeSourceOut]:
    rows = (
        await session.execute(
            select(KnowledgeSource, func.count(KnowledgeDocument.id))
            .outerjoin(KnowledgeDocument, KnowledgeDocument.source_id == KnowledgeSource.id)
            .where(KnowledgeSource.user_id == user.id)
            .group_by(KnowledgeSource.id)
            .order_by(KnowledgeSource.created_at)
        )
    ).all()
    return [
        KnowledgeSourceOut(
            id=source.id,
            name=source.name,
            source_type=source.source_type,
            project_id=source.project_id,
            source_url=source.source_url,
            documents=int(count),
            last_sync_at=source.last_sync_at,
            created_at=source.created_at,
        )
        for source, count in rows
    ]


@router.post("/search")
async def search(
    body: SearchIn, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> SearchOut:
    await _check_project(session, user.id, body.project_id)
    document_ids: frozenset[uuid.UUID] | None = None
    if body.library_id is not None:
        from ezo_api.learning.service import resolve_library_documents

        _lib, doc_ids = await resolve_library_documents(
            session, user_id=user.id, library_id=body.library_id
        )
        document_ids = doc_ids

    result = await services.retriever.retrieve(
        session,
        user.id,
        body.query,
        body.project_id,
        document_ids=document_ids,
        limit=body.limit,
    )
    for index, source in enumerate(result.sources, start=1):
        source.n = index
    results: list[dict[str, Any]] = [source.to_metadata() for source in result.sources]
    return SearchOut(mode=result.mode, results=results, diagnostics=result.diagnostics)
