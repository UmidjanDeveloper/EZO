"""Story projects: the shared model behind presentations and videos."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import Project, StoryAsset, StoryProject, StoryScene
from ezo_api.schemas.stories import (
    AssetOut,
    NarrationOut,
    ReorderIn,
    SceneOut,
    ScenesIn,
    StoryIn,
    StoryOut,
    StoryPatch,
    StorySummaryOut,
    TimelineOut,
)
from ezo_api.security.audit import audit
from ezo_api.story.service import StoryBundle, StoryError

router = APIRouter(
    prefix="/api/stories", tags=["stories"], dependencies=[Depends(rate_limit("default"))]
)


def _error(exc: StoryError) -> HTTPException:
    return HTTPException(422, detail={"code": exc.code, "message": exc.message})


async def _owned(session: AsyncSession, user_id: uuid.UUID, story_id: uuid.UUID) -> StoryProject:
    story = await session.get(StoryProject, story_id)
    if story is None or story.user_id != user_id:
        raise HTTPException(404, detail="Story not found.")
    return story


async def _check_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID | None
) -> None:
    if project_id is not None:
        project = await session.get(Project, project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(404, detail="Project not found.")


def summary_out(story: StoryProject, scene_count: int) -> StorySummaryOut:
    return StorySummaryOut(
        id=story.id,
        title=story.title,
        goal=story.goal,
        audience=story.audience,
        language=story.language,
        format=story.format,
        visual_style=story.visual_style,
        aspect_ratio=story.aspect_ratio,
        project_id=story.project_id,
        scene_count=scene_count,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _asset_out(a: StoryAsset) -> AssetOut:
    return AssetOut(
        id=a.id,
        scene_id=a.scene_id,
        asset_type=a.asset_type,
        artifact_id=a.artifact_id,
        source=a.source,
        metadata=a.meta or {},
    )


def story_out(bundle: StoryBundle) -> StoryOut:
    scenes = []
    for scene in bundle.scenes:
        narration = bundle.narrations.get(scene.id)
        scenes.append(
            SceneOut(
                id=scene.id,
                index=scene.position,
                title=scene.title,
                purpose=scene.purpose,
                layout=scene.layout,
                text=scene.text,
                visual_direction=scene.visual_direction,
                speaker_notes=scene.speaker_notes,
                duration_seconds=scene.duration_seconds,
                transition=scene.transition,
                metadata=scene.meta or {},
                narration=NarrationOut(
                    text=narration.text, voice=narration.voice, timing=narration.timing or {}
                )
                if narration
                else None,
                assets=[_asset_out(a) for a in bundle.assets if a.scene_id == scene.id],
            )
        )
    timeline = [
        TimelineOut(
            scene_id=t.scene_id,
            start_seconds=t.start_seconds,
            end_seconds=t.end_seconds,
            animation=t.animation or {},
        )
        for t in bundle.timeline
    ]
    base = summary_out(bundle.story, len(scenes))
    return StoryOut(
        **base.model_dump(),
        metadata=bundle.story.meta or {},
        scenes=scenes,
        story_assets=[_asset_out(a) for a in bundle.assets if a.scene_id is None],
        timeline=timeline,
        total_seconds=max((t.end_seconds for t in bundle.timeline), default=0.0),
    )


@router.get("")
async def list_stories(
    session: SessionDep, user: CurrentUser, project_id: uuid.UUID | None = None
) -> list[StorySummaryOut]:
    statement = select(StoryProject).where(StoryProject.user_id == user.id)
    if project_id is not None:
        statement = statement.where(StoryProject.project_id == project_id)
    stories = (await session.scalars(statement.order_by(StoryProject.updated_at.desc()))).all()
    out = []
    for story in stories:
        count = await session.scalar(
            select(func.count()).select_from(StoryScene).where(StoryScene.story_id == story.id)
        )
        out.append(summary_out(story, count or 0))
    return out


@router.post("", status_code=201)
async def create_story(
    body: StoryIn, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> StoryOut:
    await _check_project(session, user.id, body.project_id)
    try:
        story = await services.stories.create(session, user.id, body)
    except StoryError as exc:
        raise _error(exc) from exc
    audit(session, user.id, "story.create", "story", story.id, {"scenes": len(body.scenes)})
    await session.commit()
    return story_out(await services.stories.bundle(session, story))


@router.get("/{story_id}")
async def get_story(
    story_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> StoryOut:
    story = await _owned(session, user.id, story_id)
    return story_out(await services.stories.bundle(session, story))


@router.patch("/{story_id}")
async def update_story(
    story_id: uuid.UUID,
    body: StoryPatch,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> StoryOut:
    story = await _owned(session, user.id, story_id)
    await services.stories.update(session, story, body)
    await session.commit()
    return story_out(await services.stories.bundle(session, story))


@router.put("/{story_id}/scenes")
async def replace_scenes(
    story_id: uuid.UUID,
    body: ScenesIn,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> StoryOut:
    story = await _owned(session, user.id, story_id)
    try:
        await services.stories.replace_scenes(session, story, body.scenes)
    except StoryError as exc:
        raise _error(exc) from exc
    await session.commit()
    return story_out(await services.stories.bundle(session, story))


@router.post("/{story_id}/scenes/reorder")
async def reorder_scenes(
    story_id: uuid.UUID,
    body: ReorderIn,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> StoryOut:
    story = await _owned(session, user.id, story_id)
    try:
        await services.stories.reorder(session, story, body.scene_ids)
    except StoryError as exc:
        raise _error(exc) from exc
    await session.commit()
    return story_out(await services.stories.bundle(session, story))


@router.post("/{story_id}/timeline")
async def build_timeline(
    story_id: uuid.UUID, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> StoryOut:
    story = await _owned(session, user.id, story_id)
    await services.stories.build_timeline(session, story)
    await session.commit()
    return story_out(await services.stories.bundle(session, story))


@router.delete("/{story_id}", status_code=204)
async def delete_story(story_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    story = await _owned(session, user.id, story_id)
    audit(session, user.id, "story.delete", "story", story.id, {"title": story.title})
    await session.delete(story)
    await session.commit()
    return Response(status_code=204)
