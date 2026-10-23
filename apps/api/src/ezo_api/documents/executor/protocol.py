"""Bounded data-only protocol; never a command, tool or source-code interface."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_SECTIONS = 1000
MEMORY_BYTES = 768 * 1024 * 1024
PIDS = 64
HARD_DEADLINE = 25
PROCESSOR_VERSION = "isolated-extraction/v1"
CONVERSION_VERSION = "isolated-conversion/v1"

# OCR runs inside the same 25-second hard watchdog. The child stops on its own soft
# budget first so it can report a fixed status instead of being killed mid-page.
# Larger scans are refused (never silently truncated). Tune only with measured
# evidence from the executor image; never by stretching HARD_DEADLINE.
OcrLanguage = Literal["eng", "uzb", "uzb_cyrl", "rus"]
OCR_LANGUAGES: tuple[OcrLanguage, ...] = ("eng", "uzb", "uzb_cyrl", "rus")
MAX_OCR_PAGES = 6
OCR_SOFT_BUDGET_SECONDS = 19.0
OCR_DPI = 200
OCR_PAGE_SECONDS = 12.0

# Office → PDF with LibreOffice: OOXML only (the external-link refusal reads OOXML
# relationships; ODF links are not inspected, so ODF is not accepted).
ConvertFormat = Literal["docx", "xlsx", "pptx"]
MAX_CONVERTED_PDF_BYTES = 10 * 1024 * 1024
MAX_CONVERTED_PAGES = 500
CONVERT_SECONDS = 20.0

ExtractFormat = Literal["pdf", "docx", "epub", "png", "jpeg"]


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: Literal["extract"] = "extract"
    format: ExtractFormat
    data_base64: str = Field(max_length=4 * ((MAX_INPUT_BYTES + 2) // 3))
    ocr_languages: tuple[OcrLanguage, ...] = Field(default=(), max_length=len(OCR_LANGUAGES))
    """Empty: no OCR. Only used when a PDF has no text layer, or for images."""


class ConversionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: Literal["convert_pdf"]
    format: ConvertFormat
    data_base64: str = Field(max_length=4 * ((MAX_INPUT_BYTES + 2) // 3))


ExecutorRequest = TypeAdapter(
    Annotated[ExtractionRequest | ConversionRequest, Field(discriminator="operation")]
)


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


class OcrSummary(BaseModel):
    """What OCR did. Confidence is Tesseract's engine score, not calibrated accuracy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["completed", "page_limit", "deadline", "unavailable", "no_text"]
    engine: str = Field(default="", max_length=120)
    languages: list[OcrLanguage] = Field(default_factory=list, max_length=len(OCR_LANGUAGES))
    pages: int = Field(default=0, ge=0, le=2000)
    pages_read: int = Field(default=0, ge=0, le=MAX_OCR_PAGES)
    mean_confidence: float | None = Field(default=None, ge=0, le=100)
    low_confidence_pages: list[int] = Field(default_factory=list, max_length=MAX_OCR_PAGES)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    processor_version: Literal["isolated-extraction/v1"] = "isolated-extraction/v1"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(max_length=MAX_TEXT_CHARS)
    sections: list[SourceSection] = Field(max_length=MAX_SECTIONS)
    needs_ocr: bool = False
    ocr: OcrSummary | None = None
    """Present only when OCR was required; `needs_ocr` stays true unless it completed."""

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
        if self.ocr is not None and self.ocr.status == "completed" and self.needs_ocr:
            raise ValueError("Completed OCR cannot still need OCR")
        return self


class ConversionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    processor_version: Literal["isolated-conversion/v1"] = "isolated-conversion/v1"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pdf_base64: str = Field(max_length=4 * ((MAX_CONVERTED_PDF_BYTES + 2) // 3))
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: int = Field(ge=1, le=MAX_CONVERTED_PAGES)
    engine: str = Field(max_length=120)


class ExecutorError(RuntimeError):
    """Fixed safe categories: raw native stderr/input is never exposed or logged."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Isolated document processing failed: " + code)
