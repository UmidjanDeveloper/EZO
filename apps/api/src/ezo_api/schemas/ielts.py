"""Pydantic schemas for IELTS Examiner 2.0."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CueCardOut(BaseModel):
    id: str
    task: str
    points: list[str]
    follow_up: str
    discussion: list[str]


class IeltsSessionCreate(BaseModel):
    conversation_id: uuid.UUID | None = None
    target_band: float | None = Field(default=None, ge=4.0, le=9.0)


class IeltsSessionOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    status: str
    ielts_part: int | None
    cue_card: str | None
    current_prompt: str | None
    answered_count: int
    finished: bool
    band_low: float | None
    band_high: float | None
    feedback: str | None
    started_at: datetime
    ended_at: datetime | None


class IeltsAdvanceIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=5000)
    speech_seconds: float | None = Field(default=None, ge=0.0, le=600.0)


class IeltsAdvanceOut(BaseModel):
    session_id: uuid.UUID
    part: int
    instruction: str
    finished: bool
    cue_card: CueCardOut | None = None
    estimated_band_low: float | None = None
    estimated_band_high: float | None = None
    feedback: str | None = None
    explanation_uz: str | None = None


class IeltsEvaluateIn(BaseModel):
    answer: str = Field(..., min_length=3, max_length=5000)
    part: int = Field(default=1, ge=1, le=3)
    target_band: float | None = Field(default=None, ge=4.0, le=9.0)


class IeltsEvaluateOut(BaseModel):
    fluency_score: float | None = None
    lexical_score: float | None = None
    grammar_score: float | None = None
    pronunciation_score: float | None = None
    estimated_band_low: float | None = None
    estimated_band_high: float | None = None
    estimated_band: float | None = None
    constructive_feedback: str
    explanation_uz: str
    disclaimer: str = (
        "Rasmiy IELTS sertifikati emas. AI yoki talaffuz baholashi bajarilmagan. "
        "Text practice only; not an AI assessment or IELTS band estimate."
    )


class IeltsStatsOut(BaseModel):
    total_sessions: int
    completed_sessions: int
    average_band: float | None
    best_band: float | None
    total_speaking_minutes: float
    common_mistakes: list[str]


class VoiceStatusOut(BaseModel):
    available: bool
    provider: str
    fallback_mode: str
    notice_uz: str
    notice_en: str
    details: dict[str, Any]
