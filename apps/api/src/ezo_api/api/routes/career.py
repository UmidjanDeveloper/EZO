"""Career profile: one per user; the facts CVs and application letters are built from."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.career.profile import CareerProfileIn, from_row
from ezo_api.db.models import CareerProfile
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/career", tags=["career"], dependencies=[Depends(rate_limit("default"))]
)


async def _row(session: SessionDep, user_id: object) -> CareerProfile | None:
    return await session.scalar(select(CareerProfile).where(CareerProfile.user_id == user_id))


@router.get("/profile")
async def get_profile(session: SessionDep, user: CurrentUser) -> CareerProfileIn | None:
    row = await _row(session, user.id)
    return from_row(row) if row else None


@router.put("/profile")
async def put_profile(
    body: CareerProfileIn, session: SessionDep, user: CurrentUser
) -> CareerProfileIn:
    data = body.model_dump(mode="json")
    data["full_name"] = body.full_name.strip()
    row = await _row(session, user.id)
    if row is None:
        row = CareerProfile(user_id=user.id, **data)
        session.add(row)
    else:
        for key, value in data.items():
            setattr(row, key, value)
    await session.flush()
    audit(session, user.id, "career_profile.update", "career_profile", row.id, {})
    await session.commit()
    return from_row(row)


@router.delete("/profile", status_code=204)
async def delete_profile(session: SessionDep, user: CurrentUser) -> Response:
    row = await _row(session, user.id)
    if row is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "No career profile."})
    await session.delete(row)
    audit(session, user.id, "career_profile.delete", "career_profile", row.id, {})
    await session.commit()
    return Response(status_code=204)
