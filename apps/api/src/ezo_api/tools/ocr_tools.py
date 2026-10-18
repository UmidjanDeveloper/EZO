"""The `ocr_tool`: read the text of an image or a (scanned) PDF → a text artifact.

PDF pages that have a text layer are read directly (method "text_layer"); pages
without one go through OCR (method "ocr"). Results already stored for an uploaded
document by ingestion are reused when the file has not changed. Pages OCR could not
read stay empty and are listed; nothing is filled in.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import KnowledgeDocument, OcrPage
from ezo_api.documents.ocr import OCRError, OCRPage, OCRResult
from ezo_api.documents.ocr.model import LOW_CONFIDENCE
from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.document_tools import artifact_entry, file_stem
from ezo_api.tools.pdf_tools import IMAGE_TYPES, FileRef, LoadedFile, load_file

PREVIEW_CHARS = 4_000


class OcrToolArgs(BaseModel):
    input: FileRef
    languages: list[str] = Field(default_factory=list, max_length=6)
    """Tesseract language packs (uzb, uzb_cyrl, rus, eng); empty = all configured."""
    pages: str | None = Field(default=None, max_length=200)
    title: str = Field(default="", max_length=200)


class PageText(BaseModel):
    number: int
    method: str  # text_layer | ocr
    text: str
    confidence: float | None = None
    languages: str = ""
    warnings: list[str] = Field(default_factory=list)


class OcrTool(Tool[OcrToolArgs]):
    name: ClassVar[str] = "ocr_tool"
    activity: ClassVar[str] = "reading"
    timeout_seconds: ClassVar[float] = 600.0
    description: ClassVar[str] = (
        "Read the text of an image or a scanned PDF with local OCR (Tesseract; Uzbek Latin "
        "and Cyrillic, Russian, English) and store it as a text file with per-page details."
    )
    args_model: ClassVar[type[BaseModel]] = OcrToolArgs

    async def run(self, args: OcrToolArgs, ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            file = await load_file(ctx, args.input)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        is_pdf = file.mime_type.startswith("application/pdf") or file.data[:5] == b"%PDF-"
        if not is_pdf and file.mime_type not in IMAGE_TYPES:
            return ToolResult(
                ok=False,
                summary="",
                error="OCR works on images (PNG, JPEG, WebP) and PDF files only.",
                data={"error_kind": "unsupported"},
            )
        ocr = ctx.services.ocr
        try:
            pages, engine_info, warnings = await self._read(ctx, args, file, is_pdf)
        except OCRError as exc:
            return ToolResult(
                ok=False,
                summary="",
                error=exc.message,
                data={"error_kind": exc.code, "ocr": ocr.status()},
            )
        except PdfError as exc:
            return ToolResult(
                ok=False, summary="", error=exc.message, data={"error_kind": exc.code}
            )
        duration = round((time.monotonic() - started) * 1000)
        text = render_text(pages)
        if not any(p.text.strip() for p in pages):
            return ToolResult(
                ok=True,
                summary="no text recognised",
                data={
                    "pages": [p.model_dump() for p in pages],
                    "warnings": warnings,
                    "engine": engine_info,
                    "empty": True,
                },
            )
        title = args.title or f"{file.title.rsplit('.', 1)[0]} — text"
        meta = {
            "operation": "ocr",
            "engine": engine_info,
            "inputs": [file.provenance()],
            "pages": [
                {k: v for k, v in p.model_dump().items() if k != "text"} | {"chars": len(p.text)}
                for p in pages
            ],
            "warnings": warnings,
            "duration_ms": duration,
            "confidence_note": "Tesseract word confidence is the engine's own score (0-100), "
            "not a calibrated accuracy.",
            "output": {"sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)},
        }
        try:
            created = await ctx.services.artifacts.create(
                ctx.session,
                ctx.user_id,
                title=title,
                artifact_type="document",
                filename=f"{file_stem(title, 'text')}.txt",
                data=text.encode("utf-8"),
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="document",
                generation_metadata=meta,
                source_references=[file.source_reference()],
                change_summary="Created",
            )
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        ocr_pages = [p for p in pages if p.method == "ocr"]
        return ToolResult(
            ok=True,
            summary=f"{len(pages)} page(s), {len(ocr_pages)} by OCR, {len(text)} chars",
            data={
                "artifacts": [artifact_entry(created)],
                "pages": [{k: v for k, v in p.model_dump().items() if k != "text"} for p in pages],
                "preview": text[:PREVIEW_CHARS],
                "truncated": len(text) > PREVIEW_CHARS,
                "warnings": warnings,
                "engine": engine_info,
            },
        )

    async def _read(
        self, ctx: ToolContext, args: OcrToolArgs, file: LoadedFile, is_pdf: bool
    ) -> tuple[list[PageText], dict[str, Any], list[str]]:
        ocr = ctx.services.ocr
        warnings: list[str] = []
        layer: dict[int, str] = {}
        targets: list[int] | None = None
        if is_pdf:
            info = await asyncio.to_thread(engine.inspect_pdf, file.data)
            wanted = (
                engine.parse_pages(args.pages, info.page_count)
                if args.pages
                else list(range(1, info.page_count + 1))
            )
            texts = await asyncio.to_thread(engine.page_texts, file.data)
            scanned = set(info.scanned_pages)
            layer = {n: texts[n - 1] for n in wanted if n not in scanned}
            targets = [n for n in wanted if n in scanned]
        engine_info: dict[str, Any] = {"text_layer": "pypdf"} if layer else {}
        recognized: dict[int, OCRPage] = {}
        if targets is None or targets:
            stored = await self._stored(ctx, args, file, targets)
            if stored is not None:
                result = stored
                engine_info["reused_from_ingestion"] = True
            else:
                if not ocr.available:
                    raise OCRError(
                        str(ocr.status().get("reason") or "OCR is not available."), "unavailable"
                    )
                result = await ocr.extract(
                    file.data, file.mime_type, languages=args.languages or None, pages=targets
                )
            engine_info |= {"ocr": result.engine, "version": result.engine_version}
            warnings += result.warnings
            recognized = {p.number: p for p in result.pages}
        pages: list[PageText] = []
        for number in sorted(set(layer) | set(recognized)):
            if number in layer:
                pages.append(PageText(number=number, method="text_layer", text=layer[number]))
            else:
                page = recognized[number]
                pages.append(
                    PageText(
                        number=number,
                        method="ocr",
                        text=page.text,
                        confidence=page.confidence,
                        languages=page.languages,
                        warnings=page.warnings,
                    )
                )
        return pages, engine_info, warnings

    async def _stored(
        self, ctx: ToolContext, args: OcrToolArgs, file: LoadedFile, targets: list[int] | None
    ) -> OCRResult | None:
        """OCR results saved by ingestion for this unchanged upload, if they cover the pages."""
        if file.ref.kind != "document" or args.languages:
            return None
        document = await ctx.session.get(KnowledgeDocument, file.ref.id)
        if document is None:
            return None
        rows = (
            await ctx.session.scalars(
                select(OcrPage)
                .where(
                    OcrPage.document_id == document.id,
                    OcrPage.user_id == ctx.user_id,
                    OcrPage.source_content_hash == document.content_hash,
                )
                .order_by(OcrPage.page_number)
            )
        ).all()
        wanted = set(targets) if targets is not None else {1}
        if not rows or not wanted <= {r.page_number for r in rows}:
            return None
        chosen = [r for r in rows if r.page_number in wanted]
        return OCRResult(
            pages=[
                OCRPage(
                    number=r.page_number,
                    text=r.text,
                    languages=r.languages,
                    confidence=r.confidence,
                    rotation=r.rotation,
                    warnings=list(r.warnings or []),
                )
                for r in chosen
            ],
            engine=chosen[0].method,
            engine_version=chosen[0].engine_version,
            warnings=[w for r in chosen for w in (r.warnings or [])],
        )


def render_text(pages: list[PageText]) -> str:
    """The text file: one block per page, with how it was read. Empty pages say so."""
    if len(pages) == 1 and pages[0].method == "ocr":
        page = pages[0]
        return page.text.strip() + "\n"
    blocks: list[str] = []
    for page in pages:
        how = "text layer" if page.method == "text_layer" else "OCR"
        if page.method == "ocr" and page.confidence is not None:
            how += f", Tesseract confidence {page.confidence:.0f}/100"
            if page.confidence < LOW_CONFIDENCE:
                how += " — low, check against the original"
        body = page.text.strip() or "[no text could be read on this page]"
        blocks.append(f"--- Page {page.number} ({how}) ---\n\n{body}")
    return "\n\n".join(blocks) + "\n"
