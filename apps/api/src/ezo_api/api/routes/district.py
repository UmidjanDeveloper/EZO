"""District center API: projects, people, progress (API / Excel / manual) and warnings.

Every row belongs to the signed-in account. Sending a warning (Telegram/SMS) needs a
draft, an explicit "send" by the installation owner, and is audited with each channel's
real result. Secrets (bot token, Eskiz password, API tokens) never leave the server.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import (
    DistrictAssignment,
    DistrictMember,
    DistrictNotice,
    DistrictProject,
    TelegramRecipient,
)
from ezo_api.district import service as district
from ezo_api.district.records import RecordsError, from_table, phone_of
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/district", tags=["district"], dependencies=[Depends(rate_limit("default"))]
)

MAX_TABLE_BYTES = 5 * 1024 * 1024


def _fail(exc: district.DistrictError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    description: str = Field(default="", max_length=2000)
    unit: str = Field(default="ta", min_length=1, max_length=40)
    responsible_org: str = Field(default="", max_length=160)
    start_date: date | None = None
    deadline: date | None = None
    status: str = Field(default="active", pattern="^(active|paused|finished)$")
    source_kind: str = Field(default="manual", pattern="^(manual|import|api)$")
    source: dict[str, Any] = Field(default_factory=dict)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    aliases: list[str] | None = Field(default=None, max_length=10)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    responsible_org: str | None = Field(default=None, max_length=160)
    start_date: date | None = None
    deadline: date | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|finished)$")
    source_kind: str | None = Field(default=None, pattern="^(manual|import|api)$")
    source: dict[str, Any] | None = None


class MemberIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    position: str = Field(default="", max_length=160)
    area: str = Field(default="", max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    external_id: str | None = Field(default=None, max_length=80)
    telegram_recipient_id: uuid.UUID | None = None


class ProgressIn(BaseModel):
    target: float | None = Field(default=None, ge=0, le=10_000_000)
    done: float | None = Field(default=None, ge=0, le=10_000_000)


class NoticeIn(BaseModel):
    project_id: uuid.UUID
    member_id: uuid.UUID
    extra: str = Field(default="", max_length=300)


class SendIn(BaseModel):
    text: str | None = Field(default=None, max_length=900)


def _project_out(row: DistrictProject) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "aliases": row.aliases or [],
        "description": row.description,
        "unit": row.unit,
        "responsible_org": row.responsible_org,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "deadline": row.deadline.isoformat() if row.deadline else None,
        "status": row.status,
        "source_kind": row.source_kind,
        "source": row.source or {},
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "last_sync_error": row.last_sync_error,
    }


def _member_out(row: DistrictMember) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "full_name": row.full_name,
        "position": row.position,
        "area": row.area,
        "phone": row.phone,
        "external_id": row.external_id,
        "telegram_recipient_id": str(row.telegram_recipient_id)
        if row.telegram_recipient_id
        else None,
    }


async def _status_out(
    session: SessionDep, services: ServicesDep, row: DistrictProject
) -> dict[str, Any]:
    status = await district.status(session, row, services.settings)
    return {
        "target": status.target,
        "done": status.done,
        "percent": status.percent,
        "expected_share": status.expected_share,
        "days_left": status.days_left,
        "behind": len(status.behind),
        "people": [
            {
                "member_id": p.member_id,
                "name": p.name,
                "area": p.area,
                "target": p.target,
                "done": p.done,
                "percent": p.percent,
                "expected": p.expected,
                "behind": p.behind,
            }
            for p in status.people
        ],
    }


def _validated_source(kind: str, source: dict[str, Any]) -> dict[str, Any]:
    if kind != "api":
        return {}
    try:
        return district.check_source(source)
    except district.DistrictError as exc:
        raise _fail(exc) from exc


@router.get("/channels")
async def channels(user: CurrentUser, services: ServicesDep) -> dict[str, Any]:
    """Which delivery channels the server is configured for (no secret is returned)."""
    from ezo_api.account.entitlements import unlimited

    settings = services.settings
    return {
        "telegram": bool(settings.telegram_bot_token),
        "sms": bool(settings.eskiz_email and settings.eskiz_password),
        "sms_sender": settings.eskiz_sender if settings.eskiz_email else None,
        "can_send": unlimited(user, settings.owner_email),
    }


@router.get("/projects")
async def list_projects(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    out = []
    for row in await district.projects(session, user.id):
        summary = await _status_out(session, services, row)
        summary.pop("people")
        out.append({**_project_out(row), "summary": summary})
    return out


@router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    existing = await session.scalar(
        select(DistrictProject).where(
            DistrictProject.user_id == user.id, DistrictProject.name == body.name.strip()
        )
    )
    if existing is not None:
        raise HTTPException(
            409, detail={"code": "exists", "message": "A project with this name exists."}
        )
    row = DistrictProject(
        user_id=user.id,
        name=body.name.strip(),
        aliases=[a.strip()[:60] for a in body.aliases if a.strip()],
        description=body.description,
        unit=body.unit.strip(),
        responsible_org=body.responsible_org.strip(),
        start_date=body.start_date,
        deadline=body.deadline,
        status=body.status,
        source_kind=body.source_kind,
        source=_validated_source(body.source_kind, body.source),
    )
    session.add(row)
    audit(session, user.id, "district.project_create", "district_project", None, {"name": row.name})
    await session.commit()
    return _project_out(row)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, project_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    progress = await _status_out(session, services, row)
    people = progress.pop("people")
    return {"project": _project_out(row), "summary": progress, "people": people}


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, project_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    data = body.model_dump(exclude_unset=True)
    kind = data.get("source_kind", row.source_kind)
    if "source" in data or "source_kind" in data:
        row.source = _validated_source(kind, data.pop("source", None) or row.source or {})
    for key, value in data.items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    audit(session, user.id, "district.project_update", "district_project", row.id, {})
    await session.commit()
    return _project_out(row)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    try:
        row = await district.project(session, user.id, project_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    await session.delete(row)
    audit(session, user.id, "district.project_delete", "district_project", project_id, {})
    await session.commit()


@router.post("/projects/{project_id}/import")
async def import_table(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, project_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    data = await file.read(MAX_TABLE_BYTES + 1)
    if len(data) > MAX_TABLE_BYTES:
        raise HTTPException(413, detail={"code": "too_large", "message": "The file is over 5 MB."})
    try:
        records = from_table(data, file.filename or "")
    except RecordsError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc
    result = await district.apply_records(session, row, records, "import")
    audit(
        session,
        user.id,
        "district.import",
        "district_project",
        row.id,
        {"rows": len(records), "updated": result.updated},
    )
    await session.commit()
    return {
        "rows": len(records),
        "created_people": result.created_people,
        "updated": result.updated,
        "unchanged": result.unchanged,
    }


@router.post("/projects/{project_id}/sync")
async def sync_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, project_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    if row.source_kind != "api":
        raise HTTPException(
            409, detail={"code": "no_api", "message": "This project has no API source."}
        )
    result = await district.sync(session, row, services.settings, services.fetcher, force=True)
    await session.commit()
    return {
        "ok": result is not None,
        "error": row.last_sync_error,
        "updated": result.updated if result else 0,
        "created_people": result.created_people if result else 0,
    }


@router.put("/projects/{project_id}/progress/{member_id}")
async def set_progress(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    body: ProgressIn,
    user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, project_id)
        person = await district.member(session, user.id, member_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    from ezo_api.district.records import Record

    result = await district.apply_records(
        session,
        row,
        [
            Record(
                name=person.full_name,
                target=body.target,
                done=body.done,
                phone=person.phone,
                external_id=person.external_id,
            )
        ],
        "manual",
    )
    await session.commit()
    return {"updated": result.updated}


@router.get("/members")
async def list_members(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(DistrictMember)
        .where(DistrictMember.user_id == user.id)
        .order_by(DistrictMember.full_name)
    )
    return [_member_out(r) for r in rows]


async def _check_recipient(
    session: SessionDep, user_id: uuid.UUID, recipient_id: uuid.UUID | None
) -> None:
    if recipient_id is None:
        return
    recipient = await session.get(TelegramRecipient, recipient_id)
    if recipient is None or recipient.user_id != user_id:
        raise HTTPException(
            404, detail={"code": "not_found", "message": "Telegram contact not found."}
        )


@router.post("/members", status_code=201)
async def create_member(body: MemberIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    phone = phone_of(body.phone) if body.phone else None
    if body.phone and phone is None:
        raise HTTPException(
            422, detail={"code": "bad_phone", "message": "Use a number like +998 90 123 45 67."}
        )
    await _check_recipient(session, user.id, body.telegram_recipient_id)
    row = DistrictMember(
        user_id=user.id,
        full_name=" ".join(body.full_name.split()),
        position=body.position,
        area=body.area,
        phone=phone,
        external_id=body.external_id,
        telegram_recipient_id=body.telegram_recipient_id,
    )
    session.add(row)
    await session.commit()
    return _member_out(row)


@router.patch("/members/{member_id}")
async def patch_member(
    member_id: uuid.UUID, body: MemberIn, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    try:
        row = await district.member(session, user.id, member_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    phone = phone_of(body.phone) if body.phone else None
    if body.phone and phone is None:
        raise HTTPException(
            422, detail={"code": "bad_phone", "message": "Use a number like +998 90 123 45 67."}
        )
    await _check_recipient(session, user.id, body.telegram_recipient_id)
    row.full_name = " ".join(body.full_name.split())
    row.position, row.area, row.phone = body.position, body.area, phone
    row.external_id = body.external_id
    row.telegram_recipient_id = body.telegram_recipient_id
    await session.commit()
    return _member_out(row)


@router.delete("/members/{member_id}", status_code=204)
async def delete_member(member_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    try:
        row = await district.member(session, user.id, member_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    await session.execute(delete(DistrictAssignment).where(DistrictAssignment.member_id == row.id))
    await session.delete(row)
    await session.commit()


@router.get("/notices")
async def list_notices(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(DistrictNotice)
        .where(DistrictNotice.user_id == user.id)
        .order_by(DistrictNotice.created_at.desc())
        .limit(200)
    )
    return [district.notice_out(r) for r in rows]


@router.post("/notices", status_code=201)
async def create_notice(
    body: NoticeIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    try:
        row = await district.project(session, user.id, body.project_id)
        person = await district.member(session, user.id, body.member_id)
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    assignment = await session.scalar(
        select(DistrictAssignment).where(
            DistrictAssignment.project_id == row.id, DistrictAssignment.member_id == person.id
        )
    )
    notice = await district.draft(
        session, services.settings, row, person, assignment, extra=body.extra
    )
    await session.commit()
    return district.notice_out(notice)


async def _own_notice(
    session: SessionDep, user_id: uuid.UUID, notice_id: uuid.UUID
) -> DistrictNotice:
    notice = await session.get(DistrictNotice, notice_id)
    if notice is None or notice.user_id != user_id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Warning not found."})
    return notice


@router.post("/notices/{notice_id}/send")
async def send_notice(
    notice_id: uuid.UUID,
    body: SendIn,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    """The approval: only the installation owner may send in the hokimiyat's name."""
    from ezo_api.account.entitlements import unlimited

    if not unlimited(user, services.settings.owner_email):
        raise HTTPException(
            403,
            detail={"code": "forbidden", "message": "Only the owner account can send warnings."},
        )
    notice = await _own_notice(session, user.id, notice_id)
    try:
        await district.send(
            session,
            services.settings,
            notice,
            user.id,
            text=body.text,
            telegram=services.district_telegram,
            sms=services.district_sms,
        )
    except district.DistrictError as exc:
        raise _fail(exc) from exc
    audit(
        session,
        user.id,
        "district.notice_send",
        "district_notice",
        notice.id,
        {
            "status": notice.status,
            "channels": notice.channels,
            "ok": {k: v.get("ok") for k, v in (notice.results or {}).items()},
        },
    )
    await session.commit()
    return district.notice_out(notice)


@router.post("/notices/{notice_id}/cancel")
async def cancel_notice(
    notice_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    notice = await _own_notice(session, user.id, notice_id)
    if notice.status != "draft":
        raise HTTPException(
            409, detail={"code": "already_handled", "message": f"Already {notice.status}."}
        )
    notice.status = "cancelled"
    await session.commit()
    return district.notice_out(notice)
