"""Professional writing: the document types EZO drafts, and organization profiles."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.api.files import file_response
from ezo_api.db.models import OrganizationAsset, OrganizationProfile
from ezo_api.organization.export import build_export
from ezo_api.organization.files import (
    MAX_FILE_BYTES,
    OrgFileError,
    check_example_file,
    check_logo,
    check_template_file,
)
from ezo_api.organization.formatting import Formatting, formatting_of
from ezo_api.organization.templates import check_template
from ezo_api.security.audit import audit
from ezo_api.tools.document_tools import file_stem
from ezo_api.writing.catalog import BY_KEY, describe

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
    formatting: Formatting = Field(default_factory=Formatting)


class OrganizationOut(OrganizationIn):
    id: uuid.UUID
    has_logo: bool = False

    model_config = {"from_attributes": True}


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    doc_type: str | None
    has_marker: bool | None = None
    excerpt: str | None = None

    model_config = {"from_attributes": True}


def _out(profile: OrganizationProfile) -> OrganizationOut:
    data = {c: getattr(profile, c) for c in OrganizationOut.model_fields if hasattr(profile, c)}
    data["formatting"] = formatting_of(profile.formatting)
    data["has_logo"] = bool(profile.logo_key)
    return OrganizationOut.model_validate(data)


def _asset_out(asset: OrganizationAsset) -> AssetOut:
    out = AssetOut.model_validate(asset)
    if asset.kind == "example" and asset.text_excerpt:
        out.excerpt = asset.text_excerpt[:300]
    return out


@router.get("/document-types")
async def document_types(_: CurrentUser) -> list[dict[str, Any]]:
    return describe()


async def _owned(session: SessionDep, user_id: uuid.UUID, org_id: uuid.UUID) -> OrganizationProfile:
    profile = await session.get(OrganizationProfile, org_id)
    if profile is None or profile.user_id != user_id:
        raise HTTPException(404, detail="Organization profile not found.")
    return profile


async def _owned_asset(
    session: SessionDep, user_id: uuid.UUID, org_id: uuid.UUID, asset_id: uuid.UUID
) -> OrganizationAsset:
    asset = await session.get(OrganizationAsset, asset_id)
    if asset is None or asset.user_id != user_id or asset.organization_id != org_id:
        raise HTTPException(404, detail="File not found.")
    return asset


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
    data["formatting"] = body.formatting.model_dump()
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
    return [_out(r) for r in rows]


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
    return _out(profile)


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
    return _out(profile)


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    """Deletes the profile, its files (logo, templates, examples) and its glossary terms."""
    profile = await _owned(session, user.id, org_id)
    keys = [a.storage_key for a in await _assets(session, user.id, org_id)]
    if profile.logo_key:
        keys.append(profile.logo_key)
    await session.delete(profile)
    audit(session, user.id, "organization.delete", "organization", org_id, {"files": len(keys)})
    await session.commit()
    for key in keys:
        await services.storage.delete(key)
    return Response(status_code=204)


async def _assets(
    session: SessionDep, user_id: uuid.UUID, org_id: uuid.UUID
) -> list[OrganizationAsset]:
    return list(
        (
            await session.scalars(
                select(OrganizationAsset)
                .where(
                    OrganizationAsset.organization_id == org_id,
                    OrganizationAsset.user_id == user_id,
                )
                .order_by(OrganizationAsset.kind, OrganizationAsset.title)
            )
        ).all()
    )


def _key(user_id: uuid.UUID, org_id: uuid.UUID, name: str) -> str:
    return f"organizations/{user_id}/{org_id}/{name}"


async def _upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            413, detail={"code": "too_large", "message": "The file is larger than 10 MB."}
        )
    return data


def _rejected(exc: OrgFileError) -> HTTPException:
    return HTTPException(422, detail={"code": exc.code, "message": exc.message})


@router.put("/organizations/{org_id}/logo")
async def put_logo(
    org_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
) -> OrganizationOut:
    profile = await _owned(session, user.id, org_id)
    try:
        checked = check_logo(file.filename or "logo", await _upload(file))
    except OrgFileError as exc:
        raise _rejected(exc) from exc
    old = profile.logo_key
    profile.logo_key = _key(user.id, org_id, f"logo-{uuid.uuid4().hex}.png")
    await services.storage.put(profile.logo_key, checked.data)
    audit(session, user.id, "organization.logo", "organization", org_id, {"sha256": checked.sha256})
    await session.commit()
    if old:
        await services.storage.delete(old)
    return _out(profile)


@router.get("/organizations/{org_id}/logo")
async def get_logo(
    org_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    profile = await _owned(session, user.id, org_id)
    if not profile.logo_key:
        raise HTTPException(404, detail="No logo.")
    data = await services.storage.get(profile.logo_key)
    return file_response(data, "logo.png", "image/png", inline=True)


@router.delete("/organizations/{org_id}/logo", status_code=204)
async def delete_logo(
    org_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    profile = await _owned(session, user.id, org_id)
    key, profile.logo_key = profile.logo_key, None
    audit(session, user.id, "organization.logo_delete", "organization", org_id, {})
    await session.commit()
    if key:
        await services.storage.delete(key)
    return Response(status_code=204)


@router.get("/organizations/{org_id}/files")
async def list_files(org_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> list[AssetOut]:
    await _owned(session, user.id, org_id)
    return [_asset_out(a) for a in await _assets(session, user.id, org_id)]


@router.post("/organizations/{org_id}/files", status_code=201)
async def add_file(
    org_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
    kind: Literal["template", "example"] = Form(...),
    title: str = Form(default="", max_length=300),
    doc_type: str | None = Form(default=None, max_length=50),
) -> AssetOut:
    """An approved Word template or an example document of the organization."""
    await _owned(session, user.id, org_id)
    if doc_type and doc_type not in BY_KEY:
        raise HTTPException(
            422, detail={"code": "bad_doc_type", "message": "Unknown document type."}
        )
    data = await _upload(file)
    try:
        checked = (check_template_file if kind == "template" else check_example_file)(
            file.filename or "file", data
        )
    except OrgFileError as exc:
        raise _rejected(exc) from exc
    extension = checked.filename.rsplit(".", 1)[-1].lower() if "." in checked.filename else "bin"
    asset = OrganizationAsset(
        user_id=user.id,
        organization_id=org_id,
        kind=kind,
        title=(title.strip() or checked.filename)[:300],
        filename=checked.filename,
        mime_type=checked.mime_type,
        storage_key=_key(user.id, org_id, f"{kind}-{uuid.uuid4().hex}.{extension}"),
        size_bytes=len(checked.data),
        sha256=checked.sha256,
        doc_type=doc_type or None,
        text_excerpt=checked.text_excerpt,
    )
    await services.storage.put(asset.storage_key, checked.data)
    session.add(asset)
    await session.flush()
    audit(
        session,
        user.id,
        f"organization.{kind}_add",
        "organization",
        org_id,
        {"asset": str(asset.id), "sha256": checked.sha256, "doc_type": doc_type},
    )
    await session.commit()
    out = _asset_out(asset)
    if kind == "template":
        out.has_marker = check_template(checked.data)["has_marker"]
    return out


@router.get("/organizations/{org_id}/files/{asset_id}/download")
async def download_file(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> Response:
    asset = await _owned_asset(session, user.id, org_id, asset_id)
    data = await services.storage.get(asset.storage_key)
    return file_response(data, asset.filename, asset.mime_type)


@router.delete("/organizations/{org_id}/files/{asset_id}", status_code=204)
async def delete_file(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    session: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> Response:
    asset = await _owned_asset(session, user.id, org_id, asset_id)
    key = asset.storage_key
    await session.delete(asset)
    audit(
        session,
        user.id,
        "organization.file_delete",
        "organization",
        org_id,
        {"asset": str(asset_id)},
    )
    await session.commit()
    await services.storage.delete(key)
    return Response(status_code=204)


@router.get("/organizations/{org_id}/export")
async def export_organization(
    org_id: uuid.UUID, session: SessionDep, services: ServicesDep, user: CurrentUser
) -> Response:
    """A ZIP with profile.json, the logo, templates and examples (for backup or moving)."""
    profile = await _owned(session, user.id, org_id)
    assets = await _assets(session, user.id, org_id)
    data = await build_export(profile, assets, services.storage)
    audit(session, user.id, "organization.export", "organization", org_id, {"files": len(assets)})
    await session.commit()
    return file_response(data, f"{file_stem(profile.name, 'organization')}.zip", "application/zip")
