"""Artifacts: list, inspect, download, rename, edit (new version), restore, delete.

Every query is scoped to the current user; another user's artifact is reported
as not found. Versions are never modified or removed individually.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.artifacts.service import ArtifactError, is_text
from ezo_api.db.models import Artifact, ArtifactVersion, Conversation, Message, Project
from ezo_api.schemas.artifacts import (
    ArtifactCreateIn,
    ArtifactDetailOut,
    ArtifactExportOut,
    ArtifactOut,
    ArtifactRenameIn,
    ArtifactTextVersionIn,
    ArtifactVersionOut,
)
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/artifacts", tags=["artifacts"], dependencies=[Depends(rate_limit("default"))]
)

EXTENSION_BY_FORMAT = {
    "markdown": ".md",
    "text": ".txt",
    "csv": ".csv",
    "json": ".json",
    "html": ".html",
}
MAX_TEXT_PREVIEW_BYTES = 2_000_000


def _error(exc: ArtifactError, status: int = 422) -> HTTPException:
    return HTTPException(
        404 if exc.code == "not_found" else status,
        detail={"code": exc.code, "message": exc.message},
    )


def version_out(version: ArtifactVersion, current_id: uuid.UUID | None) -> ArtifactVersionOut:
    metadata = dict(version.generation_metadata or {})
    raw_exports = metadata.pop("exports", None) or {}
    exports = [
        ArtifactExportOut(
            name=name,
            filename=str(entry.get("filename", name)),
            mime_type=str(entry.get("mime_type", "application/octet-stream")),
            size=int(entry.get("size", 0)),
        )
        for name, entry in (raw_exports.items() if isinstance(raw_exports, dict) else [])
        if isinstance(entry, dict)
    ]
    return ArtifactVersionOut(
        id=version.id,
        version_number=version.version_number,
        filename=version.filename,
        mime_type=version.mime_type,
        file_size=version.file_size,
        content_hash=version.content_hash,
        provider=version.provider,
        model=version.model,
        created_by=version.created_by,
        change_summary=version.change_summary,
        parent_version_id=version.parent_version_id,
        generation_metadata=metadata,  # storage keys of exports are internal
        source_references=version.source_references or [],
        created_at=version.created_at,
        current=version.id == current_id,
        is_text=is_text(version.filename),
        exports=exports,
    )


async def artifact_out(session: AsyncSession, artifact: Artifact) -> ArtifactOut:
    current = (
        await session.get(ArtifactVersion, artifact.current_version_id)
        if artifact.current_version_id
        else None
    )
    count = await session.scalar(
        select(func.count())
        .select_from(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact.id)
    )
    return ArtifactOut(
        id=artifact.id,
        title=artifact.title,
        type=artifact.artifact_type,
        status=artifact.status,
        project_id=artifact.project_id,
        conversation_id=artifact.conversation_id,
        created_by_agent=artifact.created_by_agent,
        provider=artifact.provider,
        model=artifact.model,
        metadata=artifact.meta or {},
        source_references=artifact.source_references or [],
        current_version=version_out(current, artifact.current_version_id) if current else None,
        version_count=count or 0,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


async def _owned(session: AsyncSession, user_id: uuid.UUID, artifact_id: uuid.UUID) -> Artifact:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.user_id != user_id:
        raise HTTPException(404, detail="Artifact not found.")
    return artifact


@router.get("")
async def list_artifacts(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    type: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ArtifactOut]:
    statement = select(Artifact).where(Artifact.user_id == user.id)
    if project_id is not None:
        statement = statement.where(Artifact.project_id == project_id)
    if conversation_id is not None:
        statement = statement.where(Artifact.conversation_id == conversation_id)
    if type:
        statement = statement.where(Artifact.artifact_type == type)
    rows = (
        await session.scalars(statement.order_by(Artifact.updated_at.desc()).limit(limit))
    ).all()
    return [await artifact_out(session, artifact) for artifact in rows]


@router.post("", status_code=201)
async def create_text_artifact(
    body: ArtifactCreateIn, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ArtifactOut:
    """Save text (for example one of EZO's answers) as a document artifact."""
    project_id, conversation_id = body.project_id, body.conversation_id
    sources: list[dict[str, Any]] = []
    message: Message | None = None
    if body.message_id is not None:
        message = await session.get(Message, body.message_id)
        conversation = await session.get(Conversation, message.conversation_id) if message else None
        if message is None or conversation is None or conversation.user_id != user.id:
            raise HTTPException(404, detail="Message not found.")
        conversation_id = conversation.id
        project_id = project_id or conversation.project_id
        sources = list((message.meta or {}).get("citations", []))
    if project_id is not None:
        project = await session.get(Project, project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(404, detail="Project not found.")
    if conversation_id is not None and message is None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise HTTPException(404, detail="Conversation not found.")
    try:
        result = await services.artifacts.create(
            session,
            user.id,
            title=body.title,
            artifact_type=body.type,
            filename=f"{body.title}{EXTENSION_BY_FORMAT[body.format]}",
            data=body.content.encode("utf-8"),
            project_id=project_id,
            conversation_id=conversation_id,
            metadata={"saved_from_message": str(message.id)} if message else {},
            source_references=sources,
        )
    except ArtifactError as exc:
        raise _error(exc) from exc
    if message is not None:
        refs = [
            r
            for r in (message.meta or {}).get("artifacts", [])
            if r.get("id") != str(result.artifact.id)
        ]
        refs.append(
            {
                "id": str(result.artifact.id),
                "title": result.artifact.title,
                "type": body.type,
                "version": 1,
            }
        )
        message.meta = {**(message.meta or {}), "artifacts": refs}
    audit(session, user.id, "artifact.create", "artifact", result.artifact.id, {"type": body.type})
    await session.commit()
    return await artifact_out(session, result.artifact)


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> ArtifactDetailOut:
    artifact = await _owned(session, user.id, artifact_id)
    base = await artifact_out(session, artifact)
    versions = await services.artifacts.versions(session, artifact.id)
    return ArtifactDetailOut(
        **base.model_dump(),
        versions=[version_out(v, artifact.current_version_id) for v in versions],
    )


@router.patch("/{artifact_id}")
async def rename_artifact(
    artifact_id: uuid.UUID, body: ArtifactRenameIn, session: SessionDep, user: CurrentUser
) -> ArtifactOut:
    artifact = await _owned(session, user.id, artifact_id)
    artifact.title = " ".join(body.title.split())[:300]
    await session.commit()
    await session.refresh(artifact)
    return await artifact_out(session, artifact)


@router.post("/{artifact_id}/versions", status_code=201)
async def add_text_version(
    artifact_id: uuid.UUID,
    body: ArtifactTextVersionIn,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> ArtifactDetailOut:
    """Edit a text artifact: the new content becomes a new version."""
    artifact = await _owned(session, user.id, artifact_id)
    current = await services.artifacts.current_version(session, artifact)
    if current is None or not is_text(current.filename):
        raise HTTPException(
            409, detail={"code": "not_text", "message": "Only text artifacts can be edited here."}
        )
    try:
        result = await services.artifacts.add_version(
            session,
            artifact,
            filename=current.filename,
            data=body.content.encode("utf-8"),
            created_by="user",
            change_summary=body.change_summary or "Edited",
            source_references=list(current.source_references or []),
        )
    except ArtifactError as exc:
        raise _error(exc) from exc
    if result.created:
        audit(
            session,
            user.id,
            "artifact.edit",
            "artifact",
            artifact.id,
            {"version": result.version.version_number},
        )
    await session.commit()
    return await get_artifact(artifact_id, session, user, services)


@router.post("/{artifact_id}/versions/{number}/restore")
async def restore_version(
    artifact_id: uuid.UUID,
    number: int,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> ArtifactDetailOut:
    artifact = await _owned(session, user.id, artifact_id)
    try:
        result = await services.artifacts.restore(session, artifact, number)
    except ArtifactError as exc:
        raise _error(exc) from exc
    if result.created:
        audit(session, user.id, "artifact.restore", "artifact", artifact.id, {"from": number})
    await session.commit()
    return await get_artifact(artifact_id, session, user, services)


@router.get("/{artifact_id}/versions/{number}/download")
async def download_version(
    artifact_id: uuid.UUID,
    number: int,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> Response:
    artifact = await _owned(session, user.id, artifact_id)
    try:
        version = await services.artifacts.version(session, artifact.id, number)
        data = await services.artifacts.read(version)
    except ArtifactError as exc:
        raise _error(exc, 410) from exc
    return _file_response(data, version.filename, version.mime_type)


def _file_response(data: bytes, filename: str, mime_type: str, *, inline: bool = False) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode() or "artifact"
    kind = "inline" if inline else "attachment"
    disposition = f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            # Downloads are never rendered as active content in the API's origin
            # (HTML/SVG cannot run here); only PNG previews are shown inline.
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{artifact_id}/versions/{number}/exports/{name}")
async def download_export(
    artifact_id: uuid.UUID,
    number: int,
    name: str,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> Response:
    """A file derived from a version: ``pdf``, ``html``, ``spec`` or ``preview-<n>``."""
    artifact = await _owned(session, user.id, artifact_id)
    try:
        version = await services.artifacts.version(session, artifact.id, number)
        entry, data = await services.artifacts.read_export(version, name)
    except ArtifactError as exc:
        raise _error(exc, 410) from exc
    mime_type = str(entry["mime_type"])
    return _file_response(
        data, str(entry["filename"]), mime_type, inline=mime_type.startswith("image/png")
    )


@router.get("/{artifact_id}/versions/{number}/text")
async def version_text(
    artifact_id: uuid.UUID,
    number: int,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> dict[str, Any]:
    """The text of a text-type version, for preview and editing."""
    artifact = await _owned(session, user.id, artifact_id)
    try:
        version = await services.artifacts.version(session, artifact.id, number)
    except ArtifactError as exc:
        raise _error(exc) from exc
    if not is_text(version.filename) or version.file_size > MAX_TEXT_PREVIEW_BYTES:
        raise HTTPException(
            409, detail={"code": "not_text", "message": "This version is not a text file."}
        )
    data = await services.artifacts.read(version)
    return {
        "version_number": version.version_number,
        "filename": version.filename,
        "text": data.decode("utf-8", "replace"),
    }


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
    confirm: bool = Query(default=False),
) -> Response:
    """Deleting removes every version, so it must be confirmed explicitly."""
    if not confirm:
        raise HTTPException(
            400,
            detail={
                "code": "confirm_required",
                "message": "Deleting removes all versions. Repeat with confirm=true.",
            },
        )
    artifact = await _owned(session, user.id, artifact_id)
    audit(session, user.id, "artifact.delete", "artifact", artifact.id, {"title": artifact.title})
    await services.artifacts.delete(session, artifact)
    await session.commit()
    return Response(status_code=204)
