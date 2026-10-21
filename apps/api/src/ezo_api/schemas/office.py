"""Pydantic schemas for Documents & Office Workspace."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class OfficeTemplateOut(BaseModel):
    id: str
    title: str
    type: Literal["docx", "xlsx"]
    category: str
    description: str
    sample_content: dict[str, Any]


class DocumentCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    markdown: str = Field(..., min_length=5, max_length=100_000)
    letterhead: bool = False
    export_pdf: bool = True
    conversation_id: uuid.UUID | None = None


class SheetDataIn(BaseModel):
    name: str = Field(default="Sheet1", max_length=100)
    columns: list[str] = Field(min_length=1, max_length=100)
    rows: list[list[Any]] = Field(default_factory=list, max_length=20_000)


class SpreadsheetCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    sheets: list[SheetDataIn] = Field(min_length=1, max_length=20)
    format: Literal["xlsx", "csv"] = "xlsx"
    conversation_id: uuid.UUID | None = None


class OfficeArtifactOut(BaseModel):
    artifact_id: uuid.UUID
    title: str
    type: str
    filename: str
    download_url: str
    exports: dict[str, str]
    created_at: str
