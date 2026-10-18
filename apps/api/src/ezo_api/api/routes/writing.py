"""Professional writing: the document types EZO drafts, and organization profiles."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.db.models import OrganizationProfile
from ezo_api.security.audit import audit
from ezo_api.writing.catalog import describe

router = APIRouter(
    prefix="/api/writing", tags=["writing"], dependencies=[Depends(rate_limit("default"))]
)

ORG_TYPES = ("government", "university", "school", "company", "research", "nonprofit", "other")


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    org_type: str = Field(default="other", pattern="^(" + "|".join(ORG_TYPES) + ")$")
    department: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    head_position: str | None = Field(default=None, max_length=200)
    head_name: str | None = Field(default=None, max_length=200)
    letterhead: str | None = Field(default=None, max_length=2_000)
    style_notes: str | None = Field(default=None, max_length=4_000)
    terminology: dict[str, str] = Field(default_factory=dict, max_length=200)
    is_default: bool = True


class OrganizationOut(OrganizationIn):
    id: uuid.UUID

    model_config = {"from_attributes": True}


@router.get("/document-types")
async def document_types(_: CurrentUser) -> list[dict[str, Any]]:
    return describe()


async def _owned(session: SessionDep, user_id: uuid.UUID, org_id: uuid.UUID) -> OrganizationProfile:
    profile = await session.get(OrganizationProfile, org_id)
    if profile is None or profile.user_id != user_id:
        raise HTTPException(404, detail="Organization profile not found.")
    return profile


async def _single_default(session: SessionDep, user_id: uuid.UUID, keep: uuid.UUID) -> None:
    await session.execute(
        update(OrganizationProfile)
        .where(OrganizationProfile.user_id == user_id, OrganizationProfile.id != keep)
        .values(is_default=False)
    )


def _clean(body: OrganizationIn) -> dict[str, Any]:
    data = body.model_dump()
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = value.strip() or None
    data["name"] = body.name.strip()
    data["org_type"] = body.org_type
    return data


@router.get("/organizations")
async def list_organizations(session: SessionDep, user: CurrentUser) -> list[OrganizationOut]:
    rows = (
        await session.scalars(
            select(OrganizationProfile)
            .where(OrganizationProfile.user_id == user.id)
            .order_by(OrganizationProfile.is_default.desc(), OrganizationProfile.name)
        )
    ).all()
    return [OrganizationOut.model_validate(r) for r in rows]


@router.post("/organizations", status_code=201)
async def create_organization(
    body: OrganizationIn, session: SessionDep, user: CurrentUser
) -> OrganizationOut:
    profile = OrganizationProfile(user_id=user.id, **_clean(body))
    session.add(profile)
    await session.flush()
    if profile.is_default:
        await _single_default(session, user.id, profile.id)
    audit(
        session, user.id, "organization.create", "organization", profile.id, {"name": profile.name}
    )
    await session.commit()
    return OrganizationOut.model_validate(profile)


@router.put("/organizations/{org_id}")
async def update_organization(
    org_id: uuid.UUID, body: OrganizationIn, session: SessionDep, user: CurrentUser
) -> OrganizationOut:
    profile = await _owned(session, user.id, org_id)
    for key, value in _clean(body).items():
        setattr(profile, key, value)
    if profile.is_default:
        await _single_default(session, user.id, profile.id)
    audit(session, user.id, "organization.update", "organization", profile.id, {})
    await session.commit()
    await session.refresh(profile)
    return OrganizationOut.model_validate(profile)


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Response:
    profile = await _owned(session, user.id, org_id)
    await session.delete(profile)
    audit(session, user.id, "organization.delete", "organization", org_id, {})
    await session.commit()
    return Response(status_code=204)
