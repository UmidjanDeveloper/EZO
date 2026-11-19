"""Devonxona API: appeals, tasks and meetings of the signed-in account."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.chancery import service as office
from ezo_api.db.models import Appeal, GovTask, Meeting
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/chancery", tags=["chancery"], dependencies=[Depends(rate_limit("default"))]
)


class AppealIn(BaseModel):
    applicant: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=3, max_length=5000)
    contact: str = Field(default="", max_length=300)
    channel: str = Field(default="other", max_length=24)
    received_on: date | None = None
    due_on: date | None = None
    assignee: str = Field(default="", max_length=160)


class AppealPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|in_progress|answered|closed)$")
    due_on: date | None = None
    assignee: str | None = Field(default=None, max_length=160)


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=2000)
    assignee: str = Field(default="", max_length=160)
    due_on: date | None = None


class TaskPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|done|cancelled)$")
    due_on: date | None = None


def _appeal_out(appeal: Appeal, on: date) -> dict[str, Any]:
    return {
        "id": str(appeal.id),
        "number": appeal.number,
        "applicant": appeal.applicant,
        "contact": appeal.contact,
        "channel": appeal.channel,
        "summary": appeal.summary,
        "received_on": appeal.received_on.isoformat(),
        "due_on": appeal.due_on.isoformat(),
        "assignee": appeal.assignee_name,
        "assignee_known": appeal.assignee_member_id is not None,
        "status": appeal.status,
        "state": office.appeal_state(appeal, on),
        "answered_on": appeal.answered_on.isoformat() if appeal.answered_on else None,
        "answer_artifact_id": str(appeal.answer_artifact_id) if appeal.answer_artifact_id else None,
    }


def _task_out(task: GovTask, on: date) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "number": task.number,
        "title": task.title,
        "assignee": task.assignee_name,
        "assignee_known": task.assignee_member_id is not None,
        "due_on": task.due_on.isoformat() if task.due_on else None,
        "status": task.status,
        "state": office.task_state(task, on),
        "done_on": task.done_on.isoformat() if task.done_on else None,
        "meeting_id": str(task.meeting_id) if task.meeting_id else None,
    }


@router.get("/appeals")
async def list_appeals(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    on = office.today(services.settings.timezone)
    rows = await session.scalars(
        select(Appeal)
        .where(Appeal.user_id == user.id)
        .order_by(Appeal.received_on.desc(), Appeal.number.desc())
        .limit(500)
    )
    return [_appeal_out(a, on) for a in rows]


@router.post("/appeals", status_code=201)
async def create_appeal(
    body: AppealIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    on = office.today(services.settings.timezone)
    try:
        appeal = await office.create_appeal(
            session,
            user.id,
            applicant=body.applicant,
            summary=body.summary,
            contact=body.contact,
            channel=body.channel,
            received_on=min(body.received_on or on, on),
            due_on=body.due_on,
            assignee=body.assignee,
        )
    except office.ChanceryError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    audit(
        session,
        user.id,
        "chancery.appeal_create",
        "gov_appeal",
        appeal.id,
        {"number": appeal.number},
    )
    await session.commit()
    return _appeal_out(appeal, on)


@router.patch("/appeals/{appeal_id}")
async def patch_appeal(
    appeal_id: uuid.UUID,
    body: AppealPatch,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    on = office.today(services.settings.timezone)
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None or appeal.user_id != user.id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Appeal not found."})
    if body.status:
        appeal.status = body.status
        appeal.answered_on = on if body.status == "answered" else appeal.answered_on
    if body.due_on:
        appeal.due_on = body.due_on
    if body.assignee is not None:
        member = await office.find_member(session, user.id, body.assignee)
        appeal.assignee_member_id = member.id if member else None
        appeal.assignee_name = member.full_name if member else " ".join(body.assignee.split())
    await session.commit()
    return _appeal_out(appeal, on)


@router.get("/tasks")
async def list_tasks(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    on = office.today(services.settings.timezone)
    rows = await session.scalars(
        select(GovTask)
        .where(GovTask.user_id == user.id)
        .order_by(GovTask.status, GovTask.due_on.is_(None), GovTask.due_on)
        .limit(500)
    )
    return [_task_out(t, on) for t in rows]


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    on = office.today(services.settings.timezone)
    task = await office.create_task(
        session, user.id, office.TaskInput(body.title, body.assignee, body.due_on)
    )
    await session.commit()
    return _task_out(task, on)


@router.patch("/tasks/{task_id}")
async def patch_task(
    task_id: uuid.UUID,
    body: TaskPatch,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    on = office.today(services.settings.timezone)
    task = await session.get(GovTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Task not found."})
    if body.status:
        task.status = body.status
        task.done_on = on if body.status == "done" else None
    if body.due_on:
        task.due_on = body.due_on
    await session.commit()
    return _task_out(task, on)


@router.get("/meetings")
async def list_meetings(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(Meeting)
        .where(Meeting.user_id == user.id)
        .order_by(Meeting.held_on.desc())
        .limit(200)
    )
    return [
        {
            "id": str(m.id),
            "title": m.title,
            "held_on": m.held_on.isoformat(),
            "minutes_artifact_id": str(m.minutes_artifact_id) if m.minutes_artifact_id else None,
        }
        for m in rows
    ]
