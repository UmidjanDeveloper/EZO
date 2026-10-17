"""Schemas for the Language Coach. Mirrored in packages/shared/src/types.ts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LanguageSessionOut(BaseModel):
    id: uuid.UUID
    mode: str
    language: str
    status: str
    cefr_target: str | None
    cefr_estimate: str | None
    ielts_part: int | None
    started_at: datetime
    ended_at: datetime | None
    speaking_seconds: float
    user_words: int
    band_low: float | None
    band_high: float | None
    """Estimated IELTS-style range (simulator), never an official score."""
    fluency_score: float | None
    lexical_score: float | None
    grammar_score: float | None
    pronunciation_score: float | None
    pronunciation_confidence: str
    feedback: str | None
    conversation_id: uuid.UUID | None
    report_artifact_id: uuid.UUID | None


class LanguageTurnOut(BaseModel):
    position: int
    role: str
    text: str
    channel: str
    ielts_part: int | None
    word_count: int
    speech_seconds: float | None


class LanguageMetricOut(BaseModel):
    name: str
    value: float
    scale: str
    method: str
    confidence: str


class LanguageMistakeOut(BaseModel):
    category: str
    original: str
    correction: str
    explanation: str
    severity: str


class LanguageSessionDetailOut(LanguageSessionOut):
    strengths: list[str]
    weaknesses: list[str]
    practice_target: str
    notes: list[str]
    turns: list[LanguageTurnOut]
    metrics: list[LanguageMetricOut]
    mistakes: list[LanguageMistakeOut]


class RecurringMistakeOut(BaseModel):
    category: str
    count: int
    sessions: int
    example: str


class LanguageGoalIn(BaseModel):
    description: str = Field(min_length=2, max_length=300)
    target_band: float | None = Field(default=None, gt=0, le=9)
    cefr_target: str | None = Field(default=None, pattern=r"^(A1|A2|B1|B2|C1|C2)$")
    deadline: datetime | None = None


class LanguageGoalOut(BaseModel):
    id: uuid.UUID
    description: str
    target_band: float | None
    cefr_target: str | None
    deadline: datetime | None
    status: str
    created_at: datetime


class LanguageProgressOut(BaseModel):
    sessions: list[LanguageSessionOut]
    speaking_minutes: float
    criteria_trend: dict[str, dict[str, float]]
    """criterion → {"older": avg, "newer": avg} (older half vs newer half of sessions)."""
    recurring_mistakes: list[RecurringMistakeOut]
    goals: list[LanguageGoalOut]


class VocabularyItemOut(BaseModel):
    term: str
    meaning: str
    example: str
    times_suggested: int
    status: str
    created_at: datetime
    meta: dict[str, Any] = Field(default_factory=dict)
