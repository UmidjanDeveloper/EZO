"""Project endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.db.models import Project
from ezo_api.schemas.api import ProjectCreate, ProjectOut, ProjectUpdate
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/projects", tags=["projects"], dependencies=[Depends(rate_limit("default"))]
)


async def _owned(session: SessionDep, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(404, detail="Project not found.")
    return project


@router.get("")
async def list_projects(session: SessionDep, user: CurrentUser) -> list[ProjectOut]:
    rows = (
        await session.scalars(
            select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
        )
    ).all()
    return [ProjectOut.model_validate(p) for p in rows]


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, session: SessionDep, user: CurrentUser) -> ProjectOut:
    project = Project(user_id=user.id, name=body.name.strip(), description=body.description.strip())
    session.add(project)
    await session.flush()
    audit(session, user.id, "project.create", "project", project.id, {"name": project.name})
    await session.commit()
    return ProjectOut.model_validate(project)


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ProjectOut:
    return ProjectOut.model_validate(await _owned(session, user.id, project_id))


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, session: SessionDep, user: CurrentUser
) -> ProjectOut:
    project = await _owned(session, user.id, project_id)
    if body.name is not None:
        project.name = body.name.strip()
    if body.description is not None:
        project.description = body.description.strip()
    if body.status is not None:
        project.status = body.status
    await session.commit()
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    """Delete a project and its project memories. Conversations are kept (unlinked)."""
    project = await _owned(session, user.id, project_id)
    audit(session, user.id, "project.delete", "project", project.id, {"name": project.name})
    await session.delete(project)
    await session.commit()
    return Response(status_code=204)
