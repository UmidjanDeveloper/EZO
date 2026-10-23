"""Stable additive Student path contract for the Antigravity experience."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import defer

from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit
from ezo_api.api.routes.document_jobs import _call
from ezo_api.db.models import StudentLearningPath
from ezo_api.student.paths import LearningPathIn, LearningPaths, PathStateIn, summary
from ezo_api.student.study import scope

router = APIRouter(
    prefix="/api/student/learning-paths",
    tags=["student-paths"],
    dependencies=[Depends(rate_limit("default"))],
)


@router.post("", status_code=201)
async def create(
    body: LearningPathIn, user: CurrentUser, services: ServicesDep, response: Response
) -> dict[str, Any]:
    result, created = await _call(LearningPaths(services.db).create(user.id, body))
    if not created:
        response.status_code = 200
    return result


@router.get("")
async def paths(
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
) -> list[dict[str, Any]]:
    async with LearningPaths(services.db).transaction(write=False) as session:
        await _call(scope(session, user.id, project_id))
        rows = (
            await session.scalars(
                select(StudentLearningPath)
                .options(defer(StudentLearningPath.steps))
                .where(
                    StudentLearningPath.user_id == user.id,
                    StudentLearningPath.state != "deleted",
                    StudentLearningPath.project_id.is_not_distinct_from(project_id),
                )
                .order_by(StudentLearningPath.created_at.desc(), StudentLearningPath.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [summary(path) for path in rows]


@router.get("/{path_id}")
async def detail(
    path_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    limit: int = Query(10, ge=1, le=20),
) -> dict[str, Any]:
    return await _call(
        LearningPaths(services.db).evaluate(user.id, path_id, project_id, limit=limit)
    )


@router.patch("/{path_id}")
async def state(
    path_id: uuid.UUID, body: PathStateIn, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    return await _call(LearningPaths(services.db).set_state(user.id, path_id, body))


@router.delete("/{path_id}", status_code=204)
async def delete(
    path_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    project_id: uuid.UUID | None = None,
    confirm: bool = False,
) -> Response:
    await _call(LearningPaths(services.db).delete(user.id, path_id, project_id, confirm=confirm))
    return Response(status_code=204)
