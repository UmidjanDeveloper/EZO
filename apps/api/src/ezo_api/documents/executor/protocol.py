"""Bounded data-only protocol; never a command, tool or source-code interface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_SECTIONS = 1000
MEMORY_BYTES = 768 * 1024 * 1024
PIDS = 64
HARD_DEADLINE = 25
PROCESSOR_VERSION = "isolated-extraction/v1"


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["pdf", "docx", "epub"]
    data_base64: str = Field(max_length=4 * ((MAX_INPUT_BYTES + 2) // 3))


class SourceSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    page: int | None = Field(default=None, ge=1, le=2000)
    heading: str | None = Field(default=None, max_length=200)
    member: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def database_safe_metadata(self) -> SourceSection:
        if any(value is not None and "\x00" in value for value in (self.heading, self.member)):
            raise ValueError("Source metadata contains an unsupported NUL character")
        return self


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    processor_version: Literal["isolated-extraction/v1"] = "isolated-extraction/v1"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(max_length=MAX_TEXT_CHARS)
    sections: list[SourceSection] = Field(max_length=MAX_SECTIONS)
    needs_ocr: bool = False

    @model_validator(mode="after")
    def offsets(self) -> ExtractionResult:
        # PostgreSQL text/JSONB cannot store U+0000. Reject untrusted parser data
        # before publication; stripping it here would invalidate source offsets.
        if "\x00" in self.text:
            raise ValueError("Source text contains an unsupported NUL character")
        previous = 0
        for section in self.sections:
            if not previous <= section.start < section.end <= len(self.text):
                raise ValueError("Invalid exact source offsets")
            previous = section.end
        return self


class ExecutorError(RuntimeError):
    """Fixed safe categories: raw native stderr/input is never exposed or logged."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Isolated document processing failed: " + code)
