"""Create, read and edit story projects."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    Artifact,
    StoryAsset,
    StoryNarration,
    StoryProject,
    StoryScene,
    StoryTimeline,
)
from ezo_api.schemas.stories import AssetIn, SceneIn, StoryIn, StoryPatch
from ezo_api.story.timeline import plan_timeline

# Positions are moved out of the way first so the (story_id, position) unique
# constraint is never violated while scenes are reordered.
_TEMP_OFFSET = 1_000_000


class StoryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class StoryBundle:
    story: StoryProject
    scenes: list[StoryScene]
    narrations: dict[uuid.UUID, StoryNarration] = field(default_factory=dict)
    assets: list[StoryAsset] = field(default_factory=list)
    timeline: list[StoryTimeline] = field(default_factory=list)


class StoryService:
    async def _check_assets(
        self, session: AsyncSession, user_id: uuid.UUID, assets: list[AssetIn]
    ) -> None:
        """Assets may only point to artifacts the user owns."""
        for asset in assets:
            if asset.artifact_id is None:
                continue
            owner = await session.scalar(
                select(Artifact.user_id).where(Artifact.id == asset.artifact_id)
            )
            if owner != user_id:
                raise StoryError(
                    "invalid_asset", "An asset refers to an artifact that does not exist."
                )

    async def create(
        self, session: AsyncSession, user_id: uuid.UUID, data: StoryIn
    ) -> StoryProject:
        story = StoryProject(
            user_id=user_id,
            project_id=data.project_id,
            title=data.title.strip(),
            goal=data.goal,
            audience=data.audience,
            language=data.language,
            format=data.format,
            visual_style=data.visual_style,
            aspect_ratio=data.aspect_ratio,
            meta=data.metadata,
        )
        session.add(story)
        await session.flush()
        await self.replace_scenes(session, story, data.scenes)
        return story

    async def update(
        self, session: AsyncSession, story: StoryProject, patch: StoryPatch
    ) -> StoryProject:
        for name, value in patch.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(story, name, value.strip() if name == "title" else value)
        story.updated_at = utcnow()
        await session.flush()
        return story

    async def replace_scenes(
        self, session: AsyncSession, story: StoryProject, scenes: list[SceneIn]
    ) -> None:
        for scene_in in scenes:
            await self._check_assets(session, story.user_id, scene_in.assets)
        await session.execute(delete(StoryTimeline).where(StoryTimeline.story_id == story.id))
        await session.execute(
            delete(StoryAsset).where(
                StoryAsset.story_id == story.id, StoryAsset.scene_id.is_not(None)
            )
        )
        old_ids = select(StoryScene.id).where(StoryScene.story_id == story.id)
        await session.execute(delete(StoryNarration).where(StoryNarration.scene_id.in_(old_ids)))
        await session.execute(delete(StoryScene).where(StoryScene.story_id == story.id))
        await session.flush()
        for position, scene_in in enumerate(scenes):
            scene = StoryScene(
                story_id=story.id,
                position=position,
                title=scene_in.title,
                purpose=scene_in.purpose,
                layout=scene_in.layout,
                text=scene_in.text,
                visual_direction=scene_in.visual_direction,
                speaker_notes=scene_in.speaker_notes,
                duration_seconds=scene_in.duration_seconds,
                transition=scene_in.transition,
                meta=scene_in.metadata,
            )
            session.add(scene)
            await session.flush()
            if scene_in.narration is not None and scene_in.narration.text.strip():
                session.add(
                    StoryNarration(
                        scene_id=scene.id,
                        text=scene_in.narration.text,
                        voice=scene_in.narration.voice,
                        timing={},
                    )
                )
            for asset in scene_in.assets:
                session.add(
                    StoryAsset(
                        story_id=story.id,
                        scene_id=scene.id,
                        asset_type=asset.asset_type,
                        artifact_id=asset.artifact_id,
                        source=asset.source,
                        meta=asset.metadata,
                    )
                )
        story.updated_at = utcnow()
        await session.flush()

    async def reorder(
        self, session: AsyncSession, story: StoryProject, scene_ids: list[uuid.UUID]
    ) -> None:
        scenes = await self._scenes(session, story.id)
        by_id = {scene.id: scene for scene in scenes}
        if len(scene_ids) != len(scenes) or set(scene_ids) != set(by_id):
            raise StoryError(
                "invalid_order", "The new order must list every scene of the story exactly once."
            )
        for scene in scenes:
            scene.position += _TEMP_OFFSET
        await session.flush()
        for position, scene_id in enumerate(scene_ids):
            by_id[scene_id].position = position
        story.updated_at = utcnow()
        # The old timeline no longer matches the order.
        await session.execute(delete(StoryTimeline).where(StoryTimeline.story_id == story.id))
        await session.flush()

    async def build_timeline(
        self, session: AsyncSession, story: StoryProject
    ) -> list[StoryTimeline]:
        scenes = await self._scenes(session, story.id)
        narrations = await self._narrations(session, [s.id for s in scenes])
        planned = plan_timeline(
            [
                (s.duration_seconds, narrations[s.id].text if s.id in narrations else "")
                for s in scenes
            ]
        )
        await session.execute(delete(StoryTimeline).where(StoryTimeline.story_id == story.id))
        rows = [
            StoryTimeline(
                story_id=story.id,
                scene_id=scene.id,
                start_seconds=slot.start,
                end_seconds=slot.end,
                animation={"transition": scene.transition} if scene.transition else {},
            )
            for scene, slot in zip(scenes, planned, strict=True)
        ]
        session.add_all(rows)
        for scene, slot in zip(scenes, planned, strict=True):
            if scene.id in narrations:
                narrations[scene.id].timing = {"start": slot.start, "end": slot.end}
        story.updated_at = utcnow()
        await session.flush()
        return rows

    async def bundle(self, session: AsyncSession, story: StoryProject) -> StoryBundle:
        scenes = await self._scenes(session, story.id)
        narrations = await self._narrations(session, [s.id for s in scenes])
        assets = list(
            (await session.scalars(select(StoryAsset).where(StoryAsset.story_id == story.id))).all()
        )
        order = {scene.id: scene.position for scene in scenes}
        timeline = sorted(
            (
                await session.scalars(
                    select(StoryTimeline).where(StoryTimeline.story_id == story.id)
                )
            ).all(),
            key=lambda row: order.get(row.scene_id, 0),
        )
        return StoryBundle(story, scenes, narrations, assets, list(timeline))

    async def _scenes(self, session: AsyncSession, story_id: uuid.UUID) -> list[StoryScene]:
        return list(
            (
                await session.scalars(
                    select(StoryScene)
                    .where(StoryScene.story_id == story_id)
                    .order_by(StoryScene.position)
                )
            ).all()
        )

    async def _narrations(
        self, session: AsyncSession, scene_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, StoryNarration]:
        if not scene_ids:
            return {}
        rows = (
            await session.scalars(
                select(StoryNarration).where(StoryNarration.scene_id.in_(scene_ids))
            )
        ).all()
        return {row.scene_id: row for row in rows}
