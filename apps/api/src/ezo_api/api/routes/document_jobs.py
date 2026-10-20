"""Owner control plane only: no HTTP worker claim, heartbeat or publication routes."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable

from fastapi import APIRouter, Depends, HTTPException, Query

from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit
from ezo_api.knowledge.jobs.service import DocumentJobs, JobError
from ezo_api.schemas.document_jobs import JobCreate, JobOut, PublicationOut

router = APIRouter(
    prefix="/api/knowledge", tags=["document-jobs"], dependencies=[Depends(rate_limit("default"))]
)


async def _call[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except JobError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@router.post("/documents/{document_id}/jobs", response_model=JobOut, status_code=201)
async def enqueue(
    document_id: uuid.UUID, body: JobCreate, user: CurrentUser, services: ServicesDep
) -> JobOut:
    job = await _call(
        DocumentJobs(services.db).enqueue(user.id, body.project_id, document_id, body.revision_id)
    )
    return JobOut.model_validate(job)


@router.get("/document-jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID, user: CurrentUser, services: ServicesDep, project_id: uuid.UUID | None = None
) -> JobOut:
    return JobOut.model_validate(
        await _call(DocumentJobs(services.db).get(user.id, project_id, job_id))
    )


@router.post("/document-jobs/{job_id}/cancel", response_model=JobOut)
async def cancel(
    job_id: uuid.UUID, user: CurrentUser, services: ServicesDep, project_id: uuid.UUID | None = None
) -> JobOut:
    return JobOut.model_validate(
        await _call(DocumentJobs(services.db).cancel(user.id, project_id, job_id))
    )


@router.get("/document-jobs/{job_id}/result", response_model=PublicationOut)
async def result(
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
