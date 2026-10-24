from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ezo_api.schemas.api import MemoryOut, Preferences

GoalCategory = Literal["learning", "career", "language", "productivity", "personal", "other"]
GoalStatus = Literal["active", "completed", "paused", "archived"]


class PersonalGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    category: GoalCategory = "learning"
    target_date: datetime | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersonalGoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    category: GoalCategory | None = None
    target_date: datetime | None = None
    status: GoalStatus | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class PersonalGoalOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str
    category: str
    target_date: datetime | None
    status: str
    progress: float
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryConsentUpdate(BaseModel):
    consent: bool = Field(description="Explicit consent to capture memories from interactions")
    auto_memory: bool = Field(default=False, description="Enable automatic memory suggestions")
    recall: bool | None = Field(
        default=None,
        description="Use saved memories in replies. Omitted: follows consent (revoking stops it).",
    )


class PersonalIntelligenceProfile(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    memory_consent: bool
    auto_memory: bool
    memory_recall: bool
    preferences: Preferences
    memory_stats: dict[str, Any]
    goals_stats: dict[str, Any]
    learning_progress: dict[str, Any]


class MemoryExportOut(BaseModel):
    exported_at: datetime
    user_id: uuid.UUID
    total_memories: int
    memories: list[MemoryOut]
    markdown: str
