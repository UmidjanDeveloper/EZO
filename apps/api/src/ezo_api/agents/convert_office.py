"""Chat actions for EZO Office conversions that need no model:

- a scan or photo → editable Word, layout Word or searchable PDF (OCR);
- tables in a Word file, PDF or scan → Excel;
- spreadsheet operations (sort, filter, duplicates, empty rows, totals, group-by).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ezo_api.agents.base import GatherContext, Gathered, call_tool
from ezo_api.agents.office import IMAGE_MIMES, PDF_MIME, attached_files, recent_files
from ezo_api.core.text import normalize
from ezo_api.db.models import KnowledgeDocument
from ezo_api.documents.isolation import native_execution_allowed
from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.documents.spreadsheet.analysis import read_sheets
from ezo_api.documents.spreadsheet.ops import parse_sheet_request
from ezo_api.tools.convert_tools import DOCX_MIME, XLSX_MIME

CSV_MIME = "text/csv"
_SEARCHABLE = re.compile(
    r"\b(qidiriladigan|qidirish mumkin|matnli pdf|searchable|text layer|"
    r"с текстовым слоем|с поиском|поисков\w*)"
)
_LAYOUT = re.compile(
    r"\b(asl ko'rinish\w*|ko'rinishini saqla|tartibini saqla|maket\w*|xuddi o'zi\w*|layout|"
    r"same look|как в оригинале|сохрани\w* (вид|разметк\w*))"
)
_TABLES = re.compile(
    r"\b(jadval\w*\s+(\S+\s+)?(excel|xlsx)\w*|jadval\w*\s+(ajrat|chiqar|ko'chir)\w*|"
    r"extract (the )?tables?|tables? (to|into) (excel|xlsx|a spreadsheet)|"
    r"таблиц\w*\s+(в excel|в xlsx|извлеч\w*)|извлеки таблиц\w*)"
)


_CONVERT = re.compile(
    r"\b(aylantir|o'tkaz|ko'chir|convert|turn (it|this|the \w+) into|make (it|this) a|"
    r"конверт\w*|преобраз\w*|переведи в|сделай)"
)
_REFERS = re.compile(
    r"\b(shu|ushbu|bu|fayl\w*|hujjat\w*|pdf\w*|skan\w*|rasm\w*|surat\w*|jadval\w*|"
    r"this|that|attached|the file|этот|эту|этого|файл\w*|документ\w*|скан\w*|таблиц\w*)"
)


async def _files(ctx: GatherContext, mimes: tuple[str, ...]) -> list[KnowledgeDocument]:
    """Attached files of these types; without attachments, the newest such upload, but
    only when the request clearly refers to a file ("shu fayl", "this scan")."""
    attached = await attached_files(ctx.tools, ctx.turn.attachments)
    if attached:
        return [d for d in attached if d.mime_type in mimes]
    if ctx.turn.attachments or not _REFERS.search(normalize(ctx.turn.text)):
        return []
    return await recent_files(ctx.tools, mimes, 1)


async def _is_scan(ctx: GatherContext, document: KnowledgeDocument) -> bool:
    if document.mime_type in IMAGE_MIMES:
        return True
    if document.mime_type != PDF_MIME or not document.storage_key:
        return False
    data = await ctx.tools.services.storage.get(document.storage_key)
    try:
        return bool(engine.inspect_pdf(data).scanned_pages)
    except PdfError:
        return False


def _artifact_note(data: dict[str, Any], gathered: Gathered) -> None:
    gathered.artifacts.extend(data.get("artifacts", []))


async def run_ocr_export_action(ctx: GatherContext, gathered: Gathered) -> bool:
    """Scan → Word / searchable PDF."""
    norm = normalize(ctx.turn.text)
    searchable = bool(_SEARCHABLE.search(norm))
    from ezo_api.agents.document import requested_format

    to_word = requested_format(norm) == "docx" and bool(_CONVERT.search(norm))
    if not (searchable or to_word):
        return False
    files = await _files(ctx, (PDF_MIME, *IMAGE_MIMES))
    scans = [d for d in files if await _is_scan(ctx, d)]
    if not scans:
        return False  # a PDF with text → the ordinary conversion handles it
    target = (
        "searchable_pdf"
        if searchable
        else "docx_layout"
        if _LAYOUT.search(norm)
        else "docx_editable"
    )
    for document in scans[:5]:
        name = document.filename or document.title
        result = await call_tool(
            gathered,
            ctx.tools,
            "ocr_export",
            {"input": {"kind": "document", "id": str(document.id)}, "target": target},
        )
        if not result.ok:
            gathered.notes.append(
                f"“{name}” could not be converted: {result.error} Nothing was created; say so "
                "plainly."
            )
            continue
        data = result.data or {}
        _artifact_note(data, gathered)
        if target == "searchable_pdf":
            gathered.notes.append(
                f"Made a searchable PDF from “{name}” locally with OCR: the pages look exactly as "
                f"before, with an invisible text layer on page(s) {data.get('ocr_pages')} so the "
                "text can be searched and copied. Pages that already had text were not changed."
                + "".join(f"\nWARNING: {w}" for w in data.get("warnings", []))
            )
            continue
        ocr = data.get("ocr", {})
        mode = "layout-preserving" if target == "docx_layout" else "editable"
        gathered.notes.append(
            f"Converted “{name}” to an {mode} Word file with local OCR (Tesseract): "
            f"{len(ocr.get('pages', []))} page(s) read"
            + (
                f", mean engine confidence {ocr['mean_confidence']:.0f}/100 (the engine's own "
                "score, not a calibrated accuracy)"
                if ocr.get("mean_confidence") is not None
                else ""
            )
            + "."
            + (
                " Layout mode keeps lines, indentation, spacing, font sizes and page size; "
                "fonts, columns and pictures are not rebuilt."
                if target == "docx_layout"
                else " Editable mode keeps paragraphs and headings in reading order; for a "
                "closer look ask for the layout version, for the exact look a searchable PDF."
            )
            + (
                f"\nPages with no readable text (left as a visible placeholder): "
                f"{ocr['empty_pages']}"
                if ocr.get("empty_pages")
                else ""
            )
            + (
                f"\nLow-confidence pages to check: {ocr['low_confidence_pages']}"
                if ocr.get("low_confidence_pages")
                else ""
            )
            + "\nThe original file is unchanged. Never invent links."
        )
    return True


async def run_tables_action(ctx: GatherContext, gathered: Gathered) -> bool:
    if not _TABLES.search(normalize(ctx.turn.text)):
        return False
    files = await _files(ctx, (PDF_MIME, DOCX_MIME, *IMAGE_MIMES))
    if not files:
        return False
    for document in files[:5]:
        name = document.filename or document.title
        result = await call_tool(
            gathered,
            ctx.tools,
            "extract_tables",
            {"input": {"kind": "document", "id": str(document.id)}},
        )
        if not result.ok:
            gathered.notes.append(f"Tables could not be read from “{name}”: {result.error}")
            continue
        data = result.data or {}
        tables = data.get("tables", [])
        if not tables:
            gathered.notes.append(
                f"No table was found in “{name}” ({data.get('method')}). Nothing was created. "
                "Say so; tables without clear columns may not be detected."
            )
            continue
        _artifact_note(data, gathered)
        lines = [
            f"Extracted {len(tables)} table(s) from “{name}” into one Excel file (one sheet each; "
            f"method: {data.get('method')}, no AI model):",
        ]
        for table in tables[:10]:
            where = f"page {table['page']}" if table.get("page") else "document"
            lines.append(
                f"- Table {table['table']}: {table['rows']} rows × {table['columns']} "
                f"columns ({where})" + "".join(f"; WARNING: {w}" for w in table["warnings"])
            )
        for sheet in data.get("preview", [])[:2]:
            lines.append(
                f"Sheet “{sheet['name']}” columns: {sheet['columns']}; first rows: "
                f"{sheet['rows'][:3]}"
            )
        lines.append(
            "Word tables are exact; tables from PDFs and scans are detected from the layout, so "
            "ask the user to check them."
        )
        gathered.notes.append("\n".join(lines))
    return True


async def run_sheet_action(ctx: GatherContext, gathered: Gathered) -> bool:
    files = await _files(ctx, (XLSX_MIME, CSV_MIME))
    if not files:
        return False
    document = files[0]
    if not document.storage_key:
        return False
    # F20: parsing an uploaded workbook is untrusted-document processing. It belongs to
    # the isolated path like every other sheet tool; never open it in the API process.
    # Without that path, use the table the isolated document worker already extracted.
    if not native_execution_allowed():
        return await _sheet_from_extracted(ctx, gathered, document)
    data = await ctx.tools.services.storage.get(document.storage_key)
    name = document.filename or f"{document.title}.xlsx"
    try:
        sheets = await asyncio.to_thread(read_sheets, data, name)
    except Exception:  # damaged workbook: let the other actions explain
        return False
    if not sheets:
        return False
    steps = parse_sheet_request(ctx.turn.text, sheets[0].columns)
    if not steps:
        return False
    result = await call_tool(
        gathered,
        ctx.tools,
        "sheet_ops",
        {
            "input": {"kind": "document", "id": str(document.id)},
            "steps": [_step_dict(step) for step in steps],
        },
    )
    if not result.ok:
        gathered.notes.append(f"The spreadsheet could not be changed: {result.error} Say so.")
        return True
    out = result.data or {}
    _artifact_note(out, gathered)
    gathered.notes.append(
        "\n".join(
            [
                f"Spreadsheet “{document.title}” processed locally (no AI model; every number "
                "below was computed by EZO — use these exact values):",
                *[f"- {line}" for line in out.get("report", [])],
                *[f"- WARNING: {w}" for w in out.get("warnings", [])],
                f"Result: {out.get('rows')} rows; columns {out.get('columns')}; first rows "
                f"{out.get('preview', [])[:5]}.",
                "The result is a new Excel file (CSV also available); the original is unchanged.",
            ]
        )
    )
    return True


def _step_dict(step: Any) -> dict[str, Any]:
    fields = ("op", "column", "descending", "comparison", "value", "columns", "agg")
    return {f: getattr(step, f) for f in fields if getattr(step, f) not in (None, [], False)}


async def _sheet_from_extracted(ctx: GatherContext, gathered: Gathered, document: Any) -> bool:
    """Sort/filter/total a workbook from its extracted rows (CSV text, or the XLSX text the
    isolated worker produced); EZO writes the new XLSX itself."""
    import hashlib

    from ezo_api.analytics.table import TableError, load_tables
    from ezo_api.documents.spreadsheet.ops import SheetOpError, run_steps
    from ezo_api.documents.spreadsheet.writer import Sheet, coerce, render_xlsx
    from ezo_api.tools.document_tools import artifact_entry

    is_csv = getattr(document, "mime_type", "") == CSV_MIME or str(
        getattr(document, "filename", "") or ""
    ).lower().endswith(".csv")
    if not is_csv and getattr(document, "current_revision_id", None) is None:
        return False  # no text from the isolated worker yet; never open the workbook here
    try:
        tables = await load_tables(ctx.tools.session, ctx.tools.services.storage, document)
    except TableError as exc:
        gathered.notes.append(f"The spreadsheet could not be read: {exc.message} Say so.")
        return True
    table = tables[0]
    sheet = Sheet(table.name, table.columns, [[coerce(v) for v in row] for row in table.rows])
    steps = parse_sheet_request(ctx.turn.text, sheet.columns)
    if not steps:
        return False
    try:
        result = run_steps(sheet, steps)
    except SheetOpError as exc:
        gathered.notes.append(f"The spreadsheet could not be changed: {exc.message} Say so.")
        return True
    data = await asyncio.to_thread(render_xlsx, [result.sheet], document.title)
    stem = (document.title or "jadval").rsplit(".", 1)[0][:80]
    created = await ctx.tools.services.artifacts.create(
        ctx.tools.session, ctx.tools.user_id, title=f"{stem} (edited)", artifact_type="spreadsheet",
        filename=f"{stem} (edited).xlsx", data=data, project_id=ctx.tools.project_scope,
        conversation_id=ctx.tools.conversation_id, created_by_agent="document",
        generation_metadata={
            "operation": "sheet_ops", "sheet": table.name, "report": result.report,
            "warnings": result.warnings, "source": "extracted_text",
            "output": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
        },
        change_summary="Created",
    )  # fmt: skip
    gathered.artifacts.append(artifact_entry(created))
    gathered.tool_calls.append(
        {"tool": "sheet_ops", "ok": True, "summary": table.name, "error": None}
    )
    gathered.notes.append(
        "\n".join(
            [
                f"Spreadsheet “{document.title}” processed by EZO (every number computed "
                "by EZO — use these exact values):",
                *[f"- {line}" for line in result.report],
                *[f"- WARNING: {w}" for w in result.warnings],
                f"Result: {len(result.sheet.rows)} rows; first rows {result.sheet.rows[:5]}.",
                "The result is a new Excel file; the original is unchanged. Formatting "
                "and formulas of the original are not carried over (values only).",
            ]
        )
    )
    return True
