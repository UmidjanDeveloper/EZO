"""OCR provider interface.

No OCR provider is enabled yet: images and scanned PDFs keep the honest
"needs OCR" status. A provider (e.g. a vision model or Tesseract service) can be
added by implementing `OCRProvider` and registering it; EZO never pretends to
have read text it could not extract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OCRPage:
    number: int
    text: str
    confidence: float | None = None


class OCRError(Exception):
    pass


class OCRProvider(ABC):
    name: str

    @abstractmethod
    async def extract(self, data: bytes, mime_type: str, languages: list[str]) -> list[OCRPage]:
        """Extract text from an image or a scanned PDF."""


class NoOCRProvider(OCRProvider):
    name = "none"

    async def extract(self, data: bytes, mime_type: str, languages: list[str]) -> list[OCRPage]:
        raise OCRError("No OCR provider is configured; the file stays marked as “needs OCR”.")
