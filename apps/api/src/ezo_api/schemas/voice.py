"""Schemas for the voice API. Mirrored in packages/shared/src/types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VoiceAttemptOut(BaseModel):
    provider: str
    ok: bool
    kind: str | None = None
    message: str | None = None


class VoiceStatusOut(BaseModel):
    speech_to_text: list[str]
    text_to_speech: list[str]
    realtime: bool
    max_audio_mb: int
    stores_audio: bool
    browser_fallback: bool


class TranscriptOut(BaseModel):
    text: str
    language: str | None
    provider: str
    attempts: list[VoiceAttemptOut]


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: Literal["uz", "en", "ru"] | None = None
