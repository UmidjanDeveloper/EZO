"""Schemas for story projects (the shared model behind presentations and videos).

Mirrored in packages/shared/src/types.ts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StoryFormat = Literal["presentation", "video", "both"]
AspectRatio = Literal["16:9", "9:16", "1:1", "4:3", "4:5"]


class NarrationIn(BaseModel):
    text: str = Field(default="", max_length=8000)
    voice: str = Field(default="", max_length=80)


class AssetIn(BaseModel):
    asset_type: str = Field(min_length=1, max_length=30)
    artifact_id: uuid.UUID | None = None
    source: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SceneIn(BaseModel):
    title: str = Field(default="", max_length=300)
    purpose: str = Field(default="", max_length=2000)
    layout: str = Field(default="", max_length=40)
    text: str = Field(default="", max_length=20000)
    visual_direction: str = Field(default="", max_length=4000)
    speaker_notes: str = Field(default="", max_length=20000)
    duration_seconds: float = Field(default=6.0, gt=0, le=3600)
    transition: str = Field(default="", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)
    narration: NarrationIn | None = None
    assets: list[AssetIn] = Field(default_factory=list, max_length=50)


class StoryIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(default="", max_length=4000)
    audience: str = Field(default="", max_length=2000)
    language: Literal["uz", "en", "ru"] = "uz"
    format: StoryFormat = "presentation"
    visual_style: str = Field(default="", max_length=200)
    aspect_ratio: AspectRatio = "16:9"
    project_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    scenes: list[SceneIn] = Field(default_factory=list, max_length=200)


class StoryPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    goal: str | None = Field(default=None, max_length=4000)
    audience: str | None = Field(default=None, max_length=2000)
    language: Literal["uz", "en", "ru"] | None = None
    format: StoryFormat | None = None
    visual_style: str | None = Field(default=None, max_length=200)
    aspect_ratio: AspectRatio | None = None


class ScenesIn(BaseModel):
    scenes: list[SceneIn] = Field(max_length=200)


class ReorderIn(BaseModel):
    scene_ids: list[uuid.UUID] = Field(max_length=200)


class NarrationOut(BaseModel):
    text: str
    voice: str
    timing: dict[str, Any]


class AssetOut(BaseModel):
    id: uuid.UUID
    scene_id: uuid.UUID | None
    asset_type: str
    artifact_id: uuid.UUID | None
    source: str
    metadata: dict[str, Any]


class TimelineOut(BaseModel):
    scene_id: uuid.UUID
    start_seconds: float
    end_seconds: float
    animation: dict[str, Any]


class SceneOut(BaseModel):
    id: uuid.UUID
    index: int
    title: str
    purpose: str
    layout: str
    text: str
    visual_direction: str
    speaker_notes: str
    duration_seconds: float
    transition: str
    metadata: dict[str, Any]
    narration: NarrationOut | None
    assets: list[AssetOut]


class StorySummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    goal: str
    audience: str
    language: str
    format: str
    visual_style: str
    aspect_ratio: str
    project_id: uuid.UUID | None
    scene_count: int
    created_at: datetime
    updated_at: datetime


class StoryOut(StorySummaryOut):
    metadata: dict[str, Any]
    scenes: list[SceneOut]
    story_assets: list[AssetOut]
    timeline: list[TimelineOut]
    total_seconds: float
