"""Pydantic schemas for Presentation Maker 2.0."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ThemeInfoOut(BaseModel):
    name: str
    dark: bool
    background: str
    surface: str
    ink: str
    accent: str
    chart_palette: list[str]


class PresentationBriefIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    topic: str = Field(..., min_length=3, max_length=2000)
    audience: str = Field(default="general", max_length=100)
    slide_count: int = Field(default=8, ge=3, le=30)
    theme: str = Field(default="ezo", max_length=50)
    language: str = Field(default="uz", max_length=10)
    key_points: list[str] = Field(default_factory=list, max_length=20)


class SlideOutlineItem(BaseModel):
    slide_number: int
    layout: str
    title: str
    summary: str
    bullet_hints: list[str] = Field(default_factory=list)


class PresentationOutlineOut(BaseModel):
    title: str
    theme: str
    language: str
    slide_count: int
    slides: list[SlideOutlineItem]


class PresentationGenerateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    theme: str = Field(default="ezo", max_length=50)
    language: str = Field(default="uz", max_length=10)
    slides: list[SlideOutlineItem] | None = None
    conversation_id: uuid.UUID | None = None


class PresentationArtifactOut(BaseModel):
    artifact_id: uuid.UUID
    title: str
    theme: str
    slide_count: int
    pptx_download_url: str
    pdf_download_url: str
    html_preview_url: str
    qa_report: dict[str, Any]
