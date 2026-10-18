"""OCR: reading text from images and scanned PDF pages.

`TesseractOCRProvider` runs the local Tesseract engine (Apache-2.0) as a subprocess with
a fixed argument list, no shell and a timeout. `NoOCRProvider` is used when Tesseract is
not installed: files then keep the honest "needs OCR" status. EZO never fills in text
it could not read.
"""

from ezo_api.documents.ocr.model import (
    NoOCRProvider,
    OCRError,
    OCRLine,
    OCRPage,
    OCRProvider,
    OCRResult,
)
from ezo_api.documents.ocr.tesseract import TesseractOCRProvider, build_ocr_provider

__all__ = [
    "NoOCRProvider",
    "OCRError",
    "OCRLine",
    "OCRPage",
    "OCRProvider",
    "OCRResult",
    "TesseractOCRProvider",
    "build_ocr_provider",
]
