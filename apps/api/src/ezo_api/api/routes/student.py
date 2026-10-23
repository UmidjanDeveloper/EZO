"""Student reading over existing K1 revisions and the durable stored-text queue."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.api.routes.document_jobs import _call
from ezo_api.db.models import Project
from ezo_api.documents.isolation import ISOLATION_MESSAGE
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.jobs.service import DocumentJobs
from ezo_api.knowledge.uploads import UploadRejectedError
from ezo_api.schemas.document_jobs import JobOut, PublicationOut
from ezo_api.student.learning import LearningRequest

router = APIRouter(
    prefix="/api/student", tags=["student"], dependencies=[Depends(rate_limit("default"))]
)


class TextSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2_000_000)
    title: str = Field(default="Reading", min_length=1, max_length=200)
    project_id: uuid.UUID | None = None


@router.get("/status")
async def status(user: CurrentUser, services: ServicesDep) -> dict[str, object]:
    return {
        "supported_submission": "authorized_utf8_text",
        "max_input_bytes": 2_000_000,
        "worker": "stored-normalized-text/v1",
        "native_execution": "disabled",
        "raw_upload_formats": ["pdf", "docx", "epub"],
        "raw_processing": "requires_separate_dedicated_postgresql_worker",
        "ai_provider_configured": not services.router.is_offline,
        "embedding_provider_configured": services.embeddings.available,
        "blocked_formats": ["pdf", "docx", "epub", "xlsx", "image", "html"],
        "reason": ISOLATION_MESSAGE,
    }


@router.post("/readings", response_model=JobOut, status_code=201)
async def submit(
    body: TextSubmission, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> JobOut:
    if body.project_id is not None:
        owned = await session.scalar(
            select(Project.id).where(Project.id == body.project_id, Project.user_id == user.id)
        )
        if owned is None:
            raise HTTPException(404, detail="Project not found.")
    if not normalize_text(body.text):
        raise HTTPException(422, detail={"code": "empty", "message": "Reading text is empty."})
    try:
        added = await services.knowledge.add_upload(
            session, user.id, body.title + ".txt", body.text.encode(), body.project_id
        )
    except UploadRejectedError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc
    await session.commit()
    document = added.document
    if document.current_revision_id is None or not added.duplicate:
        document = await services.knowledge.ingest(session, document.id)
    if document.current_revision_id is None or document.status not in ("indexed", "partial"):
        raise HTTPException(
            409, detail={"code": "source_not_ready", "message": "The source is not ready to read."}
        )
    job = await _call(
        DocumentJobs(services.db).enqueue(
            user.id, body.project_id, document.id, document.current_revision_id
        )
    )
    return JobOut.model_validate(job)


@router.get("/readings/{job_id}", response_model=PublicationOut)
async def reading(
    job_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(4000, ge=1, le=8000),
) -> PublicationOut:
    return await _call(
        DocumentJobs(services.db).result_page(
            user.id, project_id, job_id, offset=offset, limit=limit
        )
    )


@router.post("/uploads", response_model=JobOut, status_code=201)
async def upload_raw(
    request: Request,
    user: CurrentUser,
    services: ServicesDep,
    filename: str = Query(min_length=1, max_length=200),
    project_id: uuid.UUID | None = None,
    ocr: Annotated[list[str] | None, Query(max_length=4)] = None,
    no_ocr: bool = False,
) -> JobOut:
    """PDF, DOCX, EPUB, PNG or JPEG. Scans/images are read by isolated OCR.

    `ocr` narrows the OCR languages (eng, uzb, uzb_cyrl, rus; default all four);
    `no_ocr` stores the source without OCR. OCR runs only when there is no text layer.
    """
    # Edge guard authenticates before receive and enforces a total body limit.
    # Streaming also enforces the tighter fixed Student input limit.
    from ezo_api.documents.executor.protocol import MAX_INPUT_BYTES
    from ezo_api.student.ingestion import StudentIngestion

    data = bytearray()
    async for part in request.stream():
        if len(data) + len(part) > MAX_INPUT_BYTES:
            raise HTTPException(413, detail={"code": "input_limit", "message": "Maximum 5 MiB."})
        data.extend(part)
    job = await _call(
        StudentIngestion(services.db).submit_raw(
            user.id, project_id, filename, bytes(data), [] if no_ocr else ocr
        )
    )
    return JobOut.model_validate(job)


@router.get("/library")
async def library(
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(30, ge=1, le=100),
) -> list[dict[str, object]]:
    from ezo_api.db.models import DocumentJob, KnowledgeDocument

    async with services.db.sessionmaker() as session:
        if (
            project_id is not None
            and await session.scalar(
                select(Project.id).where(Project.id == project_id, Project.user_id == user.id)
            )
            is None
        ):
            raise HTTPException(404, detail="Project not found.")
        rows = (
            await session.execute(
                select(DocumentJob, KnowledgeDocument.title)
                .join(KnowledgeDocument, KnowledgeDocument.id == DocumentJob.document_id)
                .where(
                    DocumentJob.user_id == user.id,
                    KnowledgeDocument.user_id == user.id,
                    DocumentJob.project_id.is_not_distinct_from(project_id),
                    KnowledgeDocument.project_id.is_not_distinct_from(project_id),
                )
                .order_by(DocumentJob.created_at.desc(), DocumentJob.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [
            {"job": JobOut.model_validate(row[0]).model_dump(mode="json"), "title": row[1]}
            for row in rows
        ]


@router.get("/documents/{document_id}/structure")
async def structure(
    document_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
) -> dict[str, object]:
    from ezo_api.db.models import DocumentRevision
    from ezo_api.student.ingestion import StudentIngestion

    async with services.db.sessionmaker() as session:
        doc = await _call(
            StudentIngestion(services.db)._document(session, user.id, project_id, document_id)
        )
        metadata = (
            await session.scalar(
                select(DocumentRevision.meta).where(DocumentRevision.id == doc.current_revision_id)
            )
            if doc.current_revision_id
            else None
        )
        return {
            "document_id": str(doc.id),
            "revision_id": str(doc.current_revision_id) if doc.current_revision_id else None,
            "sections": (metadata or {}).get("sections", []),
            "source_sha256": doc.content_hash,
            "offset_unit": "unicode_codepoints",
        }


@router.post("/readings/{job_id}/retry", response_model=JobOut, status_code=201)
async def retry_reading(
    job_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    ocr: Annotated[list[str] | None, Query(max_length=4)] = None,
) -> JobOut:
    """`ocr` replaces the OCR languages for the new generation (e.g. after ocr_required)."""
    from ezo_api.student.ingestion import StudentIngestion

    return JobOut.model_validate(
        await _call(StudentIngestion(services.db).retry(user.id, project_id, job_id, ocr))
    )


@router.post("/documents/{document_id}/learn", dependencies=[Depends(rate_limit("chat"))])
async def learning(
    document_id: uuid.UUID,
    body: LearningRequest,
    user: CurrentUser,
    services: ServicesDep,
    session: SessionDep,
) -> dict[str, object]:
    from ezo_api.student.learning import learn

    return await _call(learn(services, session, user.id, document_id, body))


@router.post("/documents/{document_id}/semantic-index", dependencies=[Depends(rate_limit("chat"))])
async def semantic_index(
    document_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0, le=3000),
) -> dict[str, object]:
    from ezo_api.student.indexing import index_batch

    return await _call(index_batch(services, user.id, project_id, document_id, offset))
