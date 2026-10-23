"""Fixed data-only entry point. No API, database, provider or tool access.

Fixed OCR (Tesseract) and Office (LibreOffice) binaries run only inside
`verified_executor_workload()`, which first re-checks this container's boundary.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import time
import unicodedata
from typing import TYPE_CHECKING

from ezo_api.documents.executor.boundary import verify_boundary
from ezo_api.documents.executor.epub import parse_epub
from ezo_api.documents.executor.protocol import (
    CONVERT_SECONDS,
    MAX_CONVERTED_PAGES,
    MAX_CONVERTED_PDF_BYTES,
    MAX_INPUT_BYTES,
    MAX_OCR_PAGES,
    MAX_OUTPUT_BYTES,
    MAX_TEXT_CHARS,
    OCR_DPI,
    OCR_PAGE_SECONDS,
    OCR_SOFT_BUDGET_SECONDS,
    ConversionRequest,
    ConversionResult,
    ExecutorRequest,
    ExtractionRequest,
    ExtractionResult,
    OcrLanguage,
    OcrSummary,
    SourceSection,
)
from ezo_api.documents.isolation import verified_executor_workload
from ezo_api.knowledge.parsers.base import Section
from ezo_api.knowledge.parsers.office import parse_docx
from ezo_api.knowledge.parsers.pdf import parse_pdf

if TYPE_CHECKING:
    from ezo_api.documents.ocr.tesseract import TesseractOCRProvider

__all__ = ["convert", "extract", "main", "verify_boundary"]

# Python start-up and boundary checks count against the 25 s hard watchdog too.
STARTED = time.monotonic()


def _assemble(
    parsed_sections: list[Section], members: list[str] | None = None
) -> tuple[str, list[SourceSection]]:
    parts: list[str] = []
    sections: list[SourceSection] = []
    offset = 0
    for index, section in enumerate(parsed_sections):
        text = unicodedata.normalize("NFC", section.text).strip()
        if not text:
            continue
        if parts:
            offset += 2
        end = offset + len(text)
        if end > MAX_TEXT_CHARS:
            raise ValueError("output_limit")
        sections.append(
            SourceSection(
                start=offset,
                end=end,
                page=section.page,
                heading=section.heading,
                member=members[index] if members else None,
            )
        )
        parts.append(text)
        offset = end
    return "\n\n".join(parts), sections


def _ocr_provider(languages: tuple[OcrLanguage, ...]) -> TesseractOCRProvider | None:
    from ezo_api.documents.ocr.tesseract import TesseractOCRProvider

    return TesseractOCRProvider.discover(
        languages=list(languages),
        timeout_seconds=OCR_PAGE_SECONDS,
        max_pages=MAX_OCR_PAGES,
        dpi=OCR_DPI,
    )


def _ocr(
    data: bytes, kind: str, languages: tuple[OcrLanguage, ...]
) -> tuple[list[Section], OcrSummary]:
    """OCR a scanned PDF (page by page, within the soft budget) or one image."""
    from PIL import Image

    from ezo_api.documents.ocr.model import LOW_CONFIDENCE, OCRError, OCRPage
    from ezo_api.documents.pdf import engine

    provider = _ocr_provider(languages)
    if provider is None:
        return [], OcrSummary(status="unavailable", languages=list(languages))
    used: list[OcrLanguage] = [lang for lang in languages if lang in provider.languages]
    total = engine.inspect_pdf(data).page_count if kind == "pdf" else 1
    base = OcrSummary(
        status="completed", engine=provider.version[:120], languages=used, pages=total
    )
    if total > MAX_OCR_PAGES:
        return [], base.model_copy(update={"status": "page_limit"})
    pages: list[OCRPage] = []
    for number in range(1, total + 1):
        remaining = OCR_SOFT_BUDGET_SECONDS - (time.monotonic() - STARTED)
        if remaining < 2:
            return [], base.model_copy(update={"status": "deadline", "pages_read": len(pages)})
        # Orientation detection and recognition each get at most half of what is left.
        provider.timeout_seconds = min(OCR_PAGE_SECONDS, remaining / 2)
        try:
            if kind == "pdf":
                [png] = engine.render_pages(data, [number], dpi=OCR_DPI)
                image = Image.open(io.BytesIO(png))
                image.load()
                pages.append(provider.read_image(image, number, list(used), dpi=OCR_DPI))
            else:
                result = provider.extract_sync(data, "image/" + kind, languages=list(used))
                pages.extend(result.pages)
        except OCRError as exc:
            if exc.code == "timeout":
                return [], base.model_copy(update={"status": "deadline", "pages_read": len(pages)})
            raise
    confidences = [p.confidence for p in pages if p.confidence is not None]
    sections = [Section(text=p.text, page=p.number if kind == "pdf" else None) for p in pages]
    summary = base.model_copy(
        update={
            "status": "completed" if any(p.text.strip() for p in pages) else "no_text",
            "pages_read": len(pages),
            "mean_confidence": (
                round(sum(confidences) / len(confidences), 1) if confidences else None
            ),
            "low_confidence_pages": [
                p.number
                for p in pages
                if p.confidence is not None and p.confidence < LOW_CONFIDENCE
            ],
        }
    )
    return sections, summary


def extract(request: ExtractionRequest, data: bytes) -> ExtractionResult:
    members: list[str] | None = None
    ocr: OcrSummary | None = None
    needs_ocr = False
    if request.format in ("png", "jpeg"):
        if not request.ocr_languages:
            raise ValueError("ocr_required")
        sections, ocr = _ocr(data, request.format, request.ocr_languages)
        needs_ocr = ocr.status != "completed"
    elif request.format == "epub":
        parsed = parse_epub(data)
        sections, members = parsed.sections, parsed.metadata.get("section_sources") or None
        needs_ocr = parsed.needs_ocr
    elif request.format == "docx":
        parsed = parse_docx(data, "document.docx")
        sections, members = parsed.sections, parsed.metadata.get("section_sources") or None
        needs_ocr = parsed.needs_ocr
    else:
        parsed = parse_pdf(data, "document.pdf")
        sections, needs_ocr = parsed.sections, parsed.needs_ocr
        if needs_ocr and request.ocr_languages:
            sections, ocr = _ocr(data, "pdf", request.ocr_languages)
            needs_ocr = ocr.status != "completed"
    text, out = _assemble(sections, members)
    return ExtractionResult(
        source_sha256=hashlib.sha256(data).hexdigest(),
        text=text,
        sections=out,
        needs_ocr=needs_ocr,
        ocr=ocr,
    )


def convert(request: ConversionRequest, data: bytes) -> ConversionResult:
    from ezo_api.documents.office_convert import OfficeConverter
    from ezo_api.documents.ooxml_limits import validate_ooxml

    validate_ooxml(data)  # bounded expansion/complexity before LibreOffice opens it
    converter = OfficeConverter.discover(timeout_seconds=CONVERT_SECONDS)
    if converter is None:
        raise RuntimeError("converter_unavailable")
    converted = converter.to_pdf_sync(data, request.format)
    if len(converted.pdf) > MAX_CONVERTED_PDF_BYTES or converted.pages > MAX_CONVERTED_PAGES:
        raise ValueError("output_limit")
    return ConversionResult(
        source_sha256=hashlib.sha256(data).hexdigest(),
        pdf_base64=base64.b64encode(converted.pdf).decode(),
        pdf_sha256=hashlib.sha256(converted.pdf).hexdigest(),
        pages=converted.pages,
        engine=converted.engine[:120],
    )


def main() -> int:
    try:
        with verified_executor_workload():
            request = ExecutorRequest.validate_json(sys.stdin.buffer.read(7 * 1024 * 1024 + 1))
            data = base64.b64decode(request.data_base64, validate=True)
            if len(data) > MAX_INPUT_BYTES:
                raise ValueError("input_limit")
            if isinstance(request, ConversionRequest):
                result: ExtractionResult | ConversionResult = convert(request, data)
            else:
                result = extract(request, data)
        output = result.model_dump_json().encode()
        if len(output) > MAX_OUTPUT_BYTES:
            raise ValueError("output_limit")
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        # Native libraries can put private paths/text into their exception strings.
        sys.stderr.write(json.dumps({"code": "invalid_document_or_resource_limit"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
