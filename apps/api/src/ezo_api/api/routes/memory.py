"""Memory endpoints: the user can inspect, add, edit and delete what EZO remembers."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import Memory, Project
from ezo_api.memory.sensitive import sensitive_reason
from ezo_api.memory.service import MemoryService
from ezo_api.schemas.api import MemoryCreate, MemoryOut, MemoryUpdate
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/memories", tags=["memory"], dependencies=[Depends(rate_limit("default"))]
)


async def _owned(session: SessionDep, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory:
    memory = await session.get(Memory, memory_id)
    if memory is None or memory.user_id != user_id:
        raise HTTPException(404, detail="Memory not found.")
    return memory


@router.get("")
async def list_memories(
    session: SessionDep,
    user: CurrentUser,
    memory_type: Literal["profile", "project"] | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[MemoryOut]:
    query = select(Memory).where(Memory.user_id == user.id)
    if memory_type:
        query = query.where(Memory.memory_type == memory_type)
    if project_id:
        query = query.where(Memory.project_id == project_id)
    query = query.order_by(Memory.updated_at.desc()).limit(limit)
    return [MemoryOut.model_validate(m) for m in (await session.scalars(query)).all()]


@router.post("", status_code=201)
async def create_memory(
    body: MemoryCreate, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> MemoryOut:
    if body.memory_type == "project":
        if body.project_id is None:
            raise HTTPException(422, detail="project_id is required for project memories.")
        project = await session.get(Project, body.project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(404, detail="Project not found.")
    memory = Memory(
        user_id=user.id,
        project_id=body.project_id if body.memory_type == "project" else None,
        memory_type=body.memory_type,
        category=body.category,
        content=body.content.strip(),
        source="user",
        confidence=1.0,
        importance=body.importance,
        # User-added memories are kept even if sensitive, but flagged so the UI
        # can warn. Automatic capture never stores sensitive content.
        sensitive=sensitive_reason(body.content) is not None,
    )
    session.add(memory)
    await session.flush()
    await MemoryService(session, services.memory_index).index_memories([memory])
    audit(session, user.id, "memory.create", "memory", memory.id, {"source": "user"})
    await session.commit()
    return MemoryOut.model_validate(memory)


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> MemoryOut:
    memory = await _owned(session, user.id, memory_id)
    if body.content is not None:
        memory.content = body.content.strip()
        memory.sensitive = sensitive_reason(memory.content) is not None
        await MemoryService(session, services.memory_index).index_memories([memory])
    if body.importance is not None:
        memory.importance = body.importance
    if body.category is not None:
        memory.category = body.category
    audit(
        session,
        user.id,
        "memory.update",
        "memory",
        memory.id,
        {"fields": sorted(body.model_fields_set)},
    )
    await session.commit()
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> Response:
    memory = await _owned(session, user.id, memory_id)
    await MemoryService(session, services.memory_index).forget_vectors([memory.id])
    audit(session, user.id, "memory.delete", "memory", memory.id, {"category": memory.category})
    await session.delete(memory)
    await session.commit()
    return Response(status_code=204)


@router.delete("", status_code=204)
async def delete_all_memories(
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
    confirm: bool = Query(default=False),
) -> Response:
    if not confirm:
        raise HTTPException(422, detail="Pass confirm=true to delete all memories.")
    ids = list((await session.scalars(select(Memory.id).where(Memory.user_id == user.id))).all())
    await MemoryService(session, services.memory_index).forget_vectors(ids)
    result = await session.execute(delete(Memory).where(Memory.user_id == user.id))
    audit(
        session,
        user.id,
        "memory.delete_all",
        "memory",
        None,
        {"count": getattr(result, "rowcount", None)},
    )
    await session.commit()
    return Response(status_code=204)


@router.get("/export")
async def export_memories(session: SessionDep, user: CurrentUser) -> dict[str, object]:
    query = select(Memory).where(Memory.user_id == user.id).order_by(Memory.updated_at.desc())
    rows = list((await session.scalars(query)).all())
    return {
        "user_id": str(user.id),
        "total_memories": len(rows),
        "memories": [MemoryOut.model_validate(m).model_dump() for m in rows],
    }
