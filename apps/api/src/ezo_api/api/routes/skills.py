"""Skills API: review the code EZO wrote, approve exactly that code, follow its runs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import Skill, SkillRun
from ezo_api.security.audit import audit
from ezo_api.skills import service as skills

router = APIRouter(
    prefix="/api/skills", tags=["skills"], dependencies=[Depends(rate_limit("default"))]
)


class ApproveIn(BaseModel):
    code_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _out(skill: Skill, *, code: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "input_hint": skill.input_hint,
        "status": skill.status,
        "code_sha256": skill.code_sha256,
        "approved": skill.approved_sha256 == skill.code_sha256 and skill.status == "approved",
        "approved_at": skill.approved_at.isoformat() if skill.approved_at else None,
        "checks": skill.checks or {},
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }
    if code:
        body["code"] = skill.code
    return body


async def _own(session: SessionDep, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.user_id != user_id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Skill not found."})
    return skill


@router.get("")
async def list_skills(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    rows = await session.scalars(
        select(Skill).where(Skill.user_id == user.id).order_by(Skill.updated_at.desc())
    )
    return {"worker": services.settings.skill_worker, "skills": [_out(s) for s in rows]}


@router.get("/{skill_id}")
async def get_skill(skill_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    skill = await _own(session, user.id, skill_id)
    runs = await session.scalars(
        select(SkillRun)
        .where(SkillRun.skill_id == skill.id)
        .order_by(SkillRun.created_at.desc())
        .limit(20)
    )
    return {
        **_out(skill, code=True),
        "runs": [
            {
                "id": str(r.id),
                "status": r.status,
                "input": r.input,
                "output": r.output,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }


@router.post("/{skill_id}/approve")
async def approve_skill(
    skill_id: uuid.UUID,
    body: ApproveIn,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    """Only the installation owner approves code that will run on this server."""
    from ezo_api.account.entitlements import unlimited

    if not unlimited(user, services.settings.owner_email):
        raise HTTPException(
            403, detail={"code": "forbidden", "message": "Only the owner can approve skills."}
        )
    skill = await _own(session, user.id, skill_id)
    try:
        await skills.approve(session, skill, body.code_sha256)
    except skills.SkillError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    audit(
        session, user.id, "skills.approve", "skill", skill.id,
        {"name": skill.name, "code_sha256": skill.code_sha256},
    )  # fmt: skip
    await session.commit()
    return _out(skill, code=True)


@router.post("/{skill_id}/disable")
async def disable_skill(
    skill_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    skill = await _own(session, user.id, skill_id)
    skill.status, skill.approved_sha256, skill.approved_at = "disabled", None, None
    audit(session, user.id, "skills.disable", "skill", skill.id, {"name": skill.name})
    await session.commit()
    return _out(skill, code=True)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    skill = await _own(session, user.id, skill_id)
    await session.delete(skill)
    audit(session, user.id, "skills.delete", "skill", skill_id, {})
    await session.commit()
