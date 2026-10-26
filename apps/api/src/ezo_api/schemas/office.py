"""Pydantic schemas for Documents & Office Workspace."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

# F21: typed, bounded cells. Excel's own cell limit is 32,767 characters.
MAX_CELL_CHARS = 32_767
MAX_TOTAL_CELLS = 200_000
Cell = Annotated[str, StringConstraints(max_length=MAX_CELL_CHARS)] | float | int | bool | None


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
    columns: list[Annotated[str, StringConstraints(max_length=300)]] = Field(
        min_length=1, max_length=100
    )
    rows: list[Annotated[list[Cell], Field(max_length=100)]] = Field(
        default_factory=list, max_length=20_000
    )


class SpreadsheetCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    sheets: list[SheetDataIn] = Field(min_length=1, max_length=20)
    format: Literal["xlsx", "csv"] = "xlsx"
    conversation_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def bounded_workbook(self) -> SpreadsheetCreateIn:
        if sum(len(row) for sheet in self.sheets for row in sheet.rows) > MAX_TOTAL_CELLS:
            raise ValueError(f"A workbook may have at most {MAX_TOTAL_CELLS} cells.")
        return self


class OfficeArtifactOut(BaseModel):
    artifact_id: uuid.UUID
    title: str
    type: str
    filename: str
    download_url: str
    exports: dict[str, str]
    created_at: str
