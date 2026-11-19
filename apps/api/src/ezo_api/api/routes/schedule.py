"""Jadval API: the owner's recurring jobs and their results."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import ScheduledJob, ScheduledRun
from ezo_api.schedule import service as schedule
from ezo_api.schedule.timing import next_run
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/schedule", tags=["schedule"], dependencies=[Depends(rate_limit("default"))]
)

Kind = Literal[
    "weekly_report", "monthly_report", "deadline_digest", "district_sync", "lexuz_recheck"
]


class JobIn(BaseModel):
    kind: Kind
    weekdays: str = Field(default="", pattern=r"^([1-7](,[1-7])*)?$")
    at_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    month_day: int | None = Field(default=None, ge=1, le=31)
    title: str | None = Field(default=None, max_length=160)
    notify_recipient_id: uuid.UUID | None = None


class JobPatch(BaseModel):
    enabled: bool | None = None
    weekdays: str | None = Field(default=None, pattern=r"^([1-7](,[1-7])*)?$")
    at_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    month_day: int | None = Field(default=None, ge=1, le=31)
    notify_recipient_id: uuid.UUID | None = None
    clear_notify: bool = False


def _job(job: ScheduledJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "title": job.title,
        "when": schedule.when(job),
        "weekdays": job.weekdays,
        "at_time": job.at_time,
        "month_day": job.month_day,
        "enabled": job.enabled,
        "notify_recipient_id": str(job.notify_recipient_id) if job.notify_recipient_id else None,
        "next_run_at": job.next_run_at.isoformat(),
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_status": job.last_status,
    }


def _run(run: ScheduledRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "status": run.status,
        "summary": run.summary,
        "error": run.error,
        "artifact_id": str(run.artifact_id) if run.artifact_id else None,
        "notified": run.notified,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def _own(session: SessionDep, user_id: uuid.UUID, job_id: uuid.UUID) -> ScheduledJob:
    job = await session.get(ScheduledJob, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Job not found."})
    return job


def _fail(exc: schedule.ScheduleError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


@router.get("")
async def list_jobs(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    jobs = await schedule.jobs_for(session, user.id)
    runs = list(
        await session.scalars(
            select(ScheduledRun)
            .where(ScheduledRun.user_id == user.id)
            .order_by(ScheduledRun.started_at.desc())
            .limit(30)
        )
    )
    return {
        "jobs": [_job(j) for j in jobs],
        "runs": [{**_run(r), "job_id": str(r.job_id)} for r in runs],
    }


@router.post("", status_code=201)
async def create(
    body: JobIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    try:
        job = await schedule.create_job(
            session, user.id, kind=body.kind, timezone=services.settings.timezone,
            weekdays=body.weekdays, at_time=body.at_time, month_day=body.month_day,
            title=body.title, notify_recipient_id=body.notify_recipient_id,
        )  # fmt: skip
    except schedule.ScheduleError as exc:
        raise _fail(exc) from exc
    audit(session, user.id, "schedule.create", "scheduled_job", job.id, {"kind": job.kind})
    await session.commit()
    return _job(job)


@router.patch("/{job_id}")
async def change(
    job_id: uuid.UUID, body: JobPatch, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    from ezo_api.db.base import utcnow
    from ezo_api.db.models import TelegramRecipient

    job = await _own(session, user.id, job_id)
    if body.enabled is not None:
        job.enabled = body.enabled
    if body.weekdays is not None:
        job.weekdays = body.weekdays
    if body.at_time is not None:
        job.at_time = body.at_time
    if body.month_day is not None:
        job.month_day = body.month_day
    if body.clear_notify:
        job.notify_recipient_id = None
    elif body.notify_recipient_id is not None:
        recipient = await session.get(TelegramRecipient, body.notify_recipient_id)
        if recipient is None or recipient.user_id != user.id or recipient.status != "verified":
            raise HTTPException(
                422, detail={"code": "recipient_not_linked", "message": "That chat is not linked."}
            )
        job.notify_recipient_id = recipient.id
    job.next_run_at = next_run(
        weekdays=job.weekdays, at_time=job.at_time, month_day=job.month_day,
        timezone=services.settings.timezone, after=utcnow(),
    )  # fmt: skip
    audit(session, user.id, "schedule.update", "scheduled_job", job.id, {"enabled": job.enabled})
    await session.commit()
    return _job(job)


@router.post("/{job_id}/run")
async def run_now(
    job_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    await _own(session, user.id, job_id)
    await session.commit()
    run = await schedule.run_job(services, job_id, manual=True)
    assert run is not None
    return _run(run)


@router.delete("/{job_id}", status_code=204)
async def delete(job_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    job = await _own(session, user.id, job_id)
    await session.delete(job)
    audit(session, user.id, "schedule.delete", "scheduled_job", job_id, {})
    await session.commit()
