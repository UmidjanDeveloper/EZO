"""OCR results with provenance: per page the text, the lines with their coordinates,
the language packs used, the engine's own word confidence, and what preprocessing did."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

LOW_CONFIDENCE = 60.0
"""Below this mean Tesseract word confidence a page gets a "check the original" warning.
Tesseract's confidence is the engine's own score (0-100), not a calibrated accuracy."""


class OCRError(Exception):
    """OCR could not run. `message` is safe to show to the user."""

    def __init__(self, message: str, code: str = "ocr_failed") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    bbox: tuple[int, int, int, int]
    """left, top, width, height in pixels of the processed page image."""
    confidence: float | None
    block: int = 0
    paragraph: int = 0


@dataclass(slots=True)
class OCRPage:
    number: int
    """1-based page of the source file (1 for a single image)."""
    text: str
    lines: list[OCRLine] = field(default_factory=list)
    width: int = 0
    height: int = 0
    dpi: int | None = None
    languages: str = ""
    """Tesseract language packs used, e.g. "uzb+eng"."""
    script: str | None = None
    """Script reported by Tesseract's orientation/script detection (Latin, Cyrillic, ...)."""
    detected_language: str | None = None
    confidence: float | None = None
    """Mean Tesseract word confidence (engine score, 0-100), None when no words."""
    rotation: int = 0
    """Degrees the page was turned (clockwise) before recognition."""
    deskew_angle: float = 0.0
    source_sha256: str = ""
    """Hash of the page image that was read (for a PDF: the rendered page)."""
    warnings: list[str] = field(default_factory=list)

    @property
    def low_confidence(self) -> bool:
        return self.confidence is not None and self.confidence < LOW_CONFIDENCE

    def lines_json(self) -> list[dict[str, Any]]:
        return [asdict(line) for line in self.lines]


@dataclass(slots=True)
class OCRResult:
    pages: list[OCRPage]
    engine: str
    engine_version: str
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def confidence(self) -> float | None:
        scored = [p for p in self.pages if p.confidence is not None]
        if not scored:
            return None
        return round(sum(p.confidence or 0 for p in scored) / len(scored), 1)

    def summary(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "engine_version": self.engine_version,
            "pages": [p.number for p in self.pages],
            "languages": sorted({p.languages for p in self.pages if p.languages}),
            "mean_confidence": self.confidence,
            "low_confidence_pages": [p.number for p in self.pages if p.low_confidence],
            "empty_pages": [p.number for p in self.pages if not p.text.strip()],
            "rotated_pages": [p.number for p in self.pages if p.rotation],
            "warnings": self.warnings[:20],
            "duration_ms": self.duration_ms,
        }


class OCRProvider(ABC):
    name: str

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        languages: list[str] | None = None,
        pages: list[int] | None = None,
    ) -> OCRResult:
        """Read an image or (selected pages of) a PDF."""

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": self.available}


class NoOCRProvider(OCRProvider):
    name = "none"

    def __init__(self, reason: str = "No OCR engine is configured.") -> None:
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        languages: list[str] | None = None,
        pages: list[int] | None = None,
    ) -> OCRResult:
        raise OCRError(self.reason, "unavailable")

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": False, "reason": self.reason}
