"""EZO Office conversions that need no model: OCR → Word / searchable PDF, tables →
Excel, and spreadsheet operations. Every result is a new artifact with provenance;
inputs are never modified."""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import zipfile
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import OcrPage
from ezo_api.documents.ocr import OCRError, OCRLine, OCRPage, TesseractOCRProvider
from ezo_api.documents.ocr.export import ocr_to_docx, searchable_pdf
from ezo_api.documents.office_convert import OfficeConvertError
from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.documents.spreadsheet.analysis import read_sheets
from ezo_api.documents.spreadsheet.ops import (
    SheetOpError,
    SheetStep,
    formula_report,
    run_steps,
)
from ezo_api.documents.spreadsheet.writer import render_csv, render_xlsx
from ezo_api.documents.tables import (
    Table,
    detect_tables,
    docx_tables,
    ocr_words,
    pdf_words,
    to_sheets,
)
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.document_tools import artifact_entry, file_stem
from ezo_api.tools.pdf_tools import IMAGE_TYPES, FileRef, LoadedFile, load_file, pdf_previews

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _is_pdf(file: LoadedFile) -> bool:
    return file.mime_type.startswith("application/pdf") or file.data[:5] == b"%PDF-"


async def _store(
    ctx: ToolContext,
    file: LoadedFile,
    *,
    title: str,
    filename: str,
    data: bytes,
    metadata: dict[str, Any],
    exports: dict[str, tuple[str, bytes]] | None = None,
    artifact_type: str = "document",
) -> dict[str, Any]:
    created = await ctx.services.artifacts.create(
        ctx.session,
        ctx.user_id,
        title=title,
        artifact_type=artifact_type,
        filename=filename,
        data=data,
        project_id=ctx.project_scope,
        conversation_id=ctx.conversation_id,
        created_by_agent="document",
        generation_metadata={
            **metadata,
            "inputs": [file.provenance()],
            "output": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
        },
        source_references=[file.source_reference()],
        exports=exports,
        change_summary="Created",
    )
    return artifact_entry(created)


# --------------------------------------------------------------------------- OCR export


class OcrExportArgs(BaseModel):
    input: FileRef
    target: Literal["docx_editable", "docx_layout", "searchable_pdf"] = "docx_editable"
    languages: list[str] = Field(default_factory=list, max_length=6)


class OcrExportTool(Tool[OcrExportArgs]):
    name: ClassVar[str] = "ocr_export"
    activity: ClassVar[str] = "reading"
    timeout_seconds: ClassVar[float] = 900.0
    description: ClassVar[str] = (
        "Turn a scan or photo into an editable Word file (plain or layout-preserving) or a "
        "searchable PDF with local OCR (Tesseract)."
    )
    args_model: ClassVar[type[BaseModel]] = OcrExportArgs

    async def run(self, args: OcrExportArgs, ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            file = await load_file(ctx, args.input)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        if not _is_pdf(file) and file.mime_type not in IMAGE_TYPES:
            return ToolResult(
                ok=False, summary="", error="Only scans (PDF) and images can be converted here."
            )
        ocr = ctx.services.ocr
        if not isinstance(ocr, TesseractOCRProvider):
            reason = str(ocr.status().get("reason") or "OCR is not available on this server.")
            return ToolResult(
                ok=False, summary="", error=reason, data={"error_kind": "unavailable"}
            )
        stem = file_stem(file.title.rsplit(".", 1)[0], "scan")
        languages = args.languages or None
        try:
            if args.target == "searchable_pdf":
                data, pages, warnings = await asyncio.to_thread(
                    searchable_pdf, ocr, file.data, file.mime_type, languages=languages
                )
                meta = {
                    "operation": "ocr_searchable_pdf",
                    "engine": ocr.version,
                    "ocr_pages": pages,
                    "warnings": warnings,
                    "note": "Page images are kept; an invisible text layer was added by "
                    "Tesseract. Pages that already had text are unchanged.",
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
                entry = await _store(
                    ctx,
                    file,
                    title=f"{stem} — searchable",
                    filename=f"{stem} (searchable).pdf",
                    data=data,
                    metadata=meta,
                )
                return ToolResult(
                    ok=True,
                    summary=f"searchable PDF, text layer on {len(pages)} page(s)",
                    data={"artifacts": [entry], "ocr_pages": pages, "warnings": warnings},
                )
            text_pages: dict[int, str] = {}
            pages_wanted: list[int] | None = None
            if _is_pdf(file):
                info = await asyncio.to_thread(engine.inspect_pdf, file.data)
                if not info.scanned_pages:
                    return ToolResult(
                        ok=False,
                        summary="",
                        error="This PDF already has a text layer; it does not need OCR.",
                        data={"error_kind": "not_needed"},
                    )
                if len(info.scanned_pages) < info.page_count:
                    pages_wanted = info.scanned_pages
                    texts = await asyncio.to_thread(engine.page_texts, file.data)
                    text_pages = {
                        n: t
                        for n, t in enumerate(texts, start=1)
                        if n not in set(info.scanned_pages)
                    }
            result = await ocr.extract(
                file.data, file.mime_type, languages=languages, pages=pages_wanted
            )
            if text_pages:
                # Pages that already had text keep it (no OCR needed); one line per line.
                result.pages = sorted(
                    [*result.pages, *(text_page(n, t) for n, t in text_pages.items())],
                    key=lambda p: p.number,
                )
        except (OCRError, PdfError) as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        mode: Literal["editable", "layout"] = (
            "layout" if args.target == "docx_layout" else "editable"
        )
        data = await asyncio.to_thread(ocr_to_docx, result, mode=mode, title=stem)
        summary = result.summary()
        meta = {
            "operation": f"ocr_docx_{mode}",
            "ocr": summary,
            "mode_note": "editable: paragraphs and headings in reading order"
            if mode == "editable"
            else "layout: lines, indentation, spacing, font size and page size of the original "
            "(fonts, columns and images are not rebuilt)",
            "confidence_note": "Tesseract confidence is the engine's own score (0-100), "
            "not a calibrated accuracy.",
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        entry = await _store(
            ctx,
            file,
            title=f"{stem} — Word ({mode})",
            filename=f"{stem} ({'layout' if mode == 'layout' else 'editable'}).docx",
            data=data,
            metadata=meta,
        )
        return ToolResult(
            ok=True,
            summary=f"Word ({mode}) from {len(result.pages)} page(s)",
            data={"artifacts": [entry], "ocr": summary, "preview": result.text[:2_000]},
        )


# --------------------------------------------------------------------------- tables


class ExtractTablesArgs(BaseModel):
    input: FileRef
    pages: str | None = Field(default=None, max_length=200)


class ExtractTablesTool(Tool[ExtractTablesArgs]):
    name: ClassVar[str] = "extract_tables"
    activity: ClassVar[str] = "reading"
    timeout_seconds: ClassVar[float] = 600.0
    description: ClassVar[str] = (
        "Find the tables in a Word file, a PDF or a scan and put each one on its own Excel sheet."
    )
    args_model: ClassVar[type[BaseModel]] = ExtractTablesArgs

    async def run(self, args: ExtractTablesArgs, ctx: ToolContext) -> ToolResult:
        try:
            file = await load_file(ctx, args.input)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        try:
            tables, method = await self._tables(ctx, file, args)
        except (OCRError, PdfError) as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        if not tables:
            return ToolResult(
                ok=True, summary="no tables found", data={"tables": [], "method": method}
            )
        sheets = to_sheets(tables)
        data = await asyncio.to_thread(render_xlsx, sheets, file.title)
        stem = file_stem(file.title.rsplit(".", 1)[0], "tables")
        described = [
            {
                "table": n,
                "page": t.page,
                "rows": len(t.rows),
                "columns": t.columns,
                "source": t.source,
                "warnings": t.warnings,
            }
            for n, t in enumerate(tables, start=1)
        ]
        meta = {
            "operation": "extract_tables",
            "method": method,
            "tables": described,
            "note": "Word tables are read exactly; PDF and scan tables are detected from the "
            "layout and may need checking.",
        }
        entry = await _store(
            ctx,
            file,
            title=f"{stem} — tables",
            filename=f"{stem} (tables).xlsx",
            data=data,
            metadata=meta,
            artifact_type="spreadsheet",
        )
        preview = [{"name": s.name, "columns": s.columns, "rows": s.rows[:5]} for s in sheets[:5]]
        return ToolResult(
            ok=True,
            summary=f"{len(tables)} table(s) → XLSX",
            data={"artifacts": [entry], "tables": described, "preview": preview, "method": method},
        )

    async def _tables(
        self, ctx: ToolContext, file: LoadedFile, args: ExtractTablesArgs
    ) -> tuple[list[Table], str]:
        if file.mime_type == DOCX_MIME or file.title.lower().endswith(".docx"):
            return await asyncio.to_thread(docx_tables, file.data), "docx structure (exact)"
        ocr = ctx.services.ocr
        if file.mime_type in IMAGE_TYPES:
            result = await ocr.extract(file.data, file.mime_type)
            lines = [line_dict(line) for page in result.pages for line in page.lines]
            return detect_tables(ocr_words(lines), source="ocr", page=None), "OCR layout"
        if not _is_pdf(file):
            return [], "unsupported"
        info = await asyncio.to_thread(engine.inspect_pdf, file.data)
        wanted = (
            engine.parse_pages(args.pages, info.page_count)
            if args.pages
            else list(range(1, min(info.page_count, 200) + 1))
        )
        scanned = set(info.scanned_pages)
        tables: list[Table] = []
        stored = await self._stored_ocr(ctx, file)
        missing_scans = [n for n in wanted if n in scanned and n not in stored]
        if missing_scans and ocr.available:
            result = await ocr.extract(file.data, file.mime_type, pages=missing_scans)
            for page in result.pages:
                stored[page.number] = [line_dict(line) for line in page.lines]
        for number in wanted:
            if number in scanned:
                if number in stored:
                    tables += detect_tables(ocr_words(stored[number]), source="ocr", page=number)
                continue
            words, _ = await asyncio.to_thread(pdf_words, file.data, number)
            tables += detect_tables(words, source="pdf_text", page=number)
        method = "PDF text layout" + (" + OCR layout" if scanned else "")
        return tables, method

    async def _stored_ocr(
        self, ctx: ToolContext, file: LoadedFile
    ) -> dict[int, list[dict[str, Any]]]:
        if file.ref.kind != "document":
            return {}
        rows = (
            await ctx.session.scalars(
                select(OcrPage).where(
                    OcrPage.document_id == file.ref.id, OcrPage.user_id == ctx.user_id
                )
            )
        ).all()
        return {r.page_number: list(r.lines or []) for r in rows if r.lines}


def text_page(number: int, text: str) -> OCRPage:
    lines = [
        OCRLine(line.strip(), (0, 0, 0, 0), None, block=index)
        for index, line in enumerate(text.splitlines())
        if line.strip()
    ]
    return OCRPage(number=number, text=text.strip(), lines=lines)


def line_dict(line: Any) -> dict[str, Any]:
    return {"text": line.text, "bbox": list(line.bbox), "words": [list(w) for w in line.words]}


# --------------------------------------------------------------------------- sheets


class SheetStepModel(BaseModel):
    op: Literal["sort", "filter", "dedupe", "drop_empty", "totals", "group"]
    column: str | None = Field(default=None, max_length=200)
    descending: bool = False
    comparison: Literal["=", "!=", ">", "<", ">=", "<=", "contains"] | None = None
    value: str | None = Field(default=None, max_length=200)
    columns: list[str] = Field(default_factory=list, max_length=30)
    agg: Literal["sum", "count", "mean", "min", "max"] = "sum"


class SheetOpsArgs(BaseModel):
    input: FileRef
    steps: list[SheetStepModel] = Field(min_length=1, max_length=10)
    sheet: str | None = Field(default=None, max_length=100)


class SheetOpsTool(Tool[SheetOpsArgs]):
    name: ClassVar[str] = "sheet_ops"
    activity: ClassVar[str] = "working"
    timeout_seconds: ClassVar[float] = 120.0
    description: ClassVar[str] = (
        "Sort, filter, de-duplicate, clean, total or group a spreadsheet (XLSX/CSV) locally; "
        "the result is a new XLSX with every number computed by EZO."
    )
    args_model: ClassVar[type[BaseModel]] = SheetOpsArgs

    async def run(self, args: SheetOpsArgs, ctx: ToolContext) -> ToolResult:
        try:
            file = await load_file(ctx, args.input)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        name = file.title if "." in file.title else f"{file.title}.xlsx"
        if not name.lower().endswith((".xlsx", ".csv")):
            return ToolResult(ok=False, summary="", error="Only XLSX and CSV files work here.")
        try:
            sheets = await asyncio.to_thread(read_sheets, file.data, name)
            formulas = await asyncio.to_thread(formula_report, file.data, name)
        except Exception as exc:  # openpyxl raises many types for damaged workbooks
            return ToolResult(
                ok=False,
                summary="",
                error=f"The spreadsheet could not be read ({type(exc).__name__}).",
            )
        if not sheets:
            return ToolResult(ok=False, summary="", error="The spreadsheet has no data.")
        sheet = next((s for s in sheets if args.sheet and s.name == args.sheet), sheets[0])
        try:
            result = run_steps(sheet, [SheetStep(**s.model_dump()) for s in args.steps])
        except SheetOpError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        warnings = list(result.warnings)
        if formulas["without_saved_result"]:
            warnings.append(
                f"{formulas['without_saved_result']} formula cell(s) have no saved result (e.g. "
                f"{', '.join(formulas['examples'])}); they were read as empty. EZO did not "
                "calculate them — open and save the file in Excel or LibreOffice first."
            )
        if len(sheets) > 1:
            warnings.append(f"Only the sheet “{sheet.name}” was processed ({len(sheets)} sheets).")
        data = await asyncio.to_thread(render_xlsx, [result.sheet], file.title)
        stem = file_stem(file.title.rsplit(".", 1)[0], "sheet")
        meta = {
            "operation": "sheet_ops",
            "steps": [s.model_dump(exclude_defaults=True) for s in args.steps],
            "sheet": sheet.name,
            "report": result.report,
            "warnings": warnings,
            "formulas": formulas,
            "rows": {"before": len(sheet.rows), "after": len(result.sheet.rows)},
            "note": "All numbers were computed by EZO and written as values (no formulas). "
            "The original formatting is not carried over.",
        }
        entry = await _store(
            ctx,
            file,
            title=f"{stem} (edited)",
            filename=f"{stem} (edited).xlsx",
            data=data,
            metadata=meta,
            exports={"csv": (f"{stem} (edited).csv", render_csv(result.sheet))},
            artifact_type="spreadsheet",
        )
        return ToolResult(
            ok=True,
            summary="; ".join(result.report)[:300],
            data={
                "artifacts": [entry],
                "report": result.report,
                "warnings": warnings,
                "columns": result.sheet.columns,
                "preview": result.sheet.rows[:10],
                "rows": len(result.sheet.rows),
            },
        )


# --------------------------------------------------------------------------- Word/Excel → PDF


class OfficePdfArgs(BaseModel):
    input: FileRef
    title: str = Field(default="", max_length=200)


def office_kind(file: LoadedFile) -> Literal["docx", "xlsx"] | None:
    name = file.title.lower()
    if file.mime_type == DOCX_MIME or name.endswith(".docx"):
        return "docx"
    if file.mime_type == XLSX_MIME or name.endswith(".xlsx"):
        return "xlsx"
    if file.data[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(file.data)).namelist()
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
    return None


class OfficePdfTool(Tool[OfficePdfArgs]):
    name: ClassVar[str] = "office_pdf"
    activity: ClassVar[str] = "working"
    timeout_seconds: ClassVar[float] = 300.0
    description: ClassVar[str] = (
        "Convert a Word (DOCX) or Excel (XLSX) file to PDF with LibreOffice, keeping its "
        "layout (styles, tables, headers, page setup, sheets)."
    )
    args_model: ClassVar[type[BaseModel]] = OfficePdfArgs

    async def run(self, args: OfficePdfArgs, ctx: ToolContext) -> ToolResult:
        converter = ctx.services.office
        if converter is None:
            return ToolResult(
                ok=False,
                summary="",
                error="LibreOffice is not installed on this server, so Word/Excel files cannot "
                "be converted with their layout.",
                data={"error_kind": "unavailable"},
            )
        try:
            file = await load_file(ctx, args.input)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        kind = office_kind(file)
        if kind is None:
            return ToolResult(
                ok=False, summary="", error="Only Word (.docx) and Excel (.xlsx) files work here."
            )
        try:
            result = await converter.to_pdf(file.data, kind)
        except OfficeConvertError as exc:
            return ToolResult(
                ok=False, summary="", error=exc.message, data={"error_kind": exc.code}
            )
        stem = file_stem(args.title or file.title.rsplit(".", 1)[0], "document")
        meta = {
            "operation": f"{kind}_to_pdf",
            "engine": result.engine,
            "pages": result.pages,
            "verification": {"reopened": True, "page_count": result.pages},
            "duration_ms": result.duration_ms,
            "note": "Laid out by LibreOffice from the original file (styles, tables, headers, "
            "page setup). Fonts missing on the server are replaced by similar ones.",
        }
        previews = await asyncio.to_thread(pdf_previews, result.pdf, result.pages, stem)
        entry = await _store(
            ctx,
            file,
            title=f"{stem} — PDF",
            filename=f"{stem}.pdf",
            data=result.pdf,
            metadata=meta,
            exports=previews,
        )
        return ToolResult(
            ok=True,
            summary=f"{kind.upper()} → PDF, {result.pages} page(s)",
            data={"artifacts": [entry], "pages": result.pages, "kind": kind},
        )
