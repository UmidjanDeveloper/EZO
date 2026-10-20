"""Student reading over existing K1 revisions and the durable stored-text queue."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
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

router = APIRouter(
    prefix="/api/student", tags=["student"], dependencies=[Depends(rate_limit("default"))]
)


class TextSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2_000_000)
    title: str = Field(default="Reading", min_length=1, max_length=200)
    project_id: uuid.UUID | None = None


@router.get("/status")
async def status(user: CurrentUser) -> dict[str, object]:
    return {
        "supported_submission": "authorized_utf8_text",
        "max_input_bytes": 2_000_000,
        "worker": "stored-normalized-text/v1",
        "native_execution": "disabled",
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
