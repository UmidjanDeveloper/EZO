# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""DocumentAgent: read, create, transform, compare and convert documents and spreadsheets.

Actions (chosen from the request, no model call needed):

    convert      → change a file's format (DOCX/PDF/MD/TXT). No model; works offline.
    compare      → paragraph-level diff of two files (difflib). No model for the facts.
    analyze      → factual column statistics of a spreadsheet; the model only explains them.
    spreadsheet  → a new XLSX built by the model from the user's data (never invented data).
    transform    → summarize / translate / proofread / rewrite / formalize a file. The result
                   is a NEW artifact (or a new version of EZO's own document) with a change
                   summary and diff statistics, so meaning changes are never silent.
    create       → write a new document (report, letter, official document) as DOCX + PDF.
    answer       → questions about the user's files (cited passages), like GeneralAgent.

Format generation lives in ``ezo_api.documents`` and runs through logged tools.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from ezo_api.agents.base import (
    Agent,
    AgentPlan,
    AgentTurn,
    GatherContext,
    Gathered,
    call_tool,
    run_tool,
)
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.convert_office import (
    run_ocr_export_action,
    run_sheet_action,
    run_tables_action,
)
from ezo_api.agents.docx_office import find_docx, run_replace_action, transform_docx
from ezo_api.agents.education_office import make_material
from ezo_api.agents.llm import complete, extract_json, sources_block
from ezo_api.agents.longdoc_office import (
    answer_sources,
    summarize_long,
    too_long_note,
    transform_long,
)
from ezo_api.agents.office import attached_files, run_ocr_action, run_pdf_action
from ezo_api.agents.references import (
    DocumentRef,
    document_source,
    find_documents,
    latest_artifact,
    refers_to_a_file,
)
from ezo_api.agents.translate_office import (
    TranslationPlan,
    docx_review,
    finish_markdown_translation,
    load_glossary,
    run_glossary_action,
    run_inline_translation,
    run_translit_action,
    translation_plan,
)
from ezo_api.agents.writing_office import write_document
from ezo_api.artifacts.service import ArtifactError
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.models import Artifact, DocumentRevision
from ezo_api.documents.compare import compare_texts
from ezo_api.documents.longdoc import TooLongError, outline
from ezo_api.documents.pdf import engine as pdf_engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.education.catalog import Kind, wants_education
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.knowledge.retrieval.sources import SourceRef, number_sources
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.storage.base import StorageError
from ezo_api.tools.base import ToolContext
from ezo_api.tools.convert_tools import DOCX_MIME, XLSX_MIME
from ezo_api.tools.document_tools import MAX_READ_CHARS
from ezo_api.translation import glossary
from ezo_api.translation.languages import DOMAIN_RULES, NAMES, base
from ezo_api.writing.catalog import DocType, wants_writing

logger = logging.getLogger(__name__)

Action = Literal["convert", "compare", "analyze", "spreadsheet", "transform", "create", "answer"]
Transform = Literal["summarize", "translate", "proofread", "rewrite", "formalize"]
Format = Literal["docx", "pdf", "md", "txt"]

SOURCE_CHARS = 40_000
"""Longest text sent for a transformation (longer files are processed in part, and the user is told)."""
ANSWER_CHARS = 20_000
SPREADSHEET_ROWS = 500

_COMPARE = re.compile(
    r"\b(solishtir|taqqosla|farqi|farqlar|compare|difference|diff\b|сравни|отлич|разниц)"
)
_CONVERT = re.compile(
    r"\b(aylantir|konvert|convert|o'gir|ko'chir|экспорт|конверт|преобраз|сохрани как|save as|export)"
)
_FORMAT_AS = re.compile(
    r"\b(pdf|word|docx|excel|xlsx)\w*\s+(qilib|qil\b|ko'rinishida|formatida|formatda|holida)"
)
_SHEET_NOUN = re.compile(r"\b(excel|xlsx|spreadsheet|jadval|таблиц|эксель)")
_MAKE = re.compile(
    r"\b(yarat|tuz|tayyorla|qil|yoz|create|make|build|draft|write|prepare|generate|созда|сделай|составь|подготов|напиши)"
)
_ANALYZE = re.compile(
    r"\b(tahlil|analy|анализ|statistik|o'rtacha|jami|sum|average|total|итог|средн|insight)"
)
_FILE_WANTED = re.compile(
    r"\b(fayl (qilib|sifatida|ko'rinishida|holida|qil)|faylga|faylda (ber|yubor)|"
    r"(as|to|into|in) a file|file (version|copy)|файлом|в файл\w*|в виде файла|"
    r"docx|word\w*|ворд|pdf (qilib|ko'rinishida|formatda)|pdfga|as (a )?pdf|в pdf|"
    r"hujjat qilib|yuklab|download|скача|документом)"
)
_TRANSFORMS: tuple[tuple[Transform, re.Pattern[str]], ...] = (
    ("translate", re.compile(r"\b(tarjima|translate|перевед|перевод|переведи)")),
    (
        "proofread",
        re.compile(
            r"\b(xatolarini tuzat|imlo|grammatik|proofread|grammar|spelling|орфограф|исправь ошибки|вычитай)"
        ),
    ),
    ("formalize", re.compile(r"\b(rasmiy uslub|rasmiylashtir|formal|официальн\w* стил)")),
    (
        "summarize",
        re.compile(r"\b(qisqacha|xulosa|qisqartir|summar|tl;?dr|резюм|кратк|конспект|выжимк)"),
    ),
    (
        "rewrite",
        re.compile(
            r"\b(qayta yoz|soddalashtir|tahrirla|rewrite|simplify|rephrase|improve|edit|перепиши|упрости|отредактир)"
        ),
    ),
)
_FORMATS: tuple[tuple[Format, re.Pattern[str]], ...] = (
    ("pdf", re.compile(r"\bpdf")),
    ("docx", re.compile(r"\b(docx|word|ворд)")),
    ("md", re.compile(r"\b(markdown|\.md\b)")),
    ("txt", re.compile(r"\b(txt|matn fayl|text file|текстов)")),
)
_LANGUAGES = {
    "uz": re.compile(r"\b(o'zbek|uzbek|узбек)"),
    "en": re.compile(r"\b(ingliz|english|англ)"),
    "ru": re.compile(r"\b(rus|russian|русск)"),
}
LANGUAGE_NAMES = {"uz": "Uzbek (Latin script)", "en": "English", "ru": "Russian"}

WRITER_FORMAT = """Reply in exactly this format:
TITLE: <document title>
CHANGES: <one sentence: what you changed, or "new document">
=====
<the document in Markdown: # title, ## headings, paragraphs, - lists, | tables |>"""

TRANSFORM_TASKS: dict[str, str] = {
    "summarize": "Summarize the document: keep its structure (headings), every key fact, number, date and name exactly; drop repetition. Aim for about a quarter of the length.",
    "translate": "Translate the whole document into {target}. Keep the structure, numbers, dates, names and legal/technical terms exact. If a term has no clear equivalent, keep the original in brackets.",
    "proofread": "Correct spelling, grammar and punctuation only. Do NOT change the meaning, facts, numbers, names or structure. Keep the author's wording wherever it is correct.",
    "rewrite": "Rewrite the document to be clearer and easier to read, as the user asks. Keep every fact, number, date and name, and do not add new claims.",
    "formalize": "Rewrite the document in a formal, official style suitable for Uzbekistan's institutions (rasmiy uslub), as the user asks. Keep every fact, number, date and name, and do not add new claims.",
}
TRANSFORM_SYSTEM = (
    """You are EZO's document editor. {task}
Never add facts that are not in the document. If something is unclear in the original, keep it and mark it with [?].

"""
    + WRITER_FORMAT
)

CREATE_SYSTEM = (
    """You are EZO's document writer. Write the document the user asks for, in {language}, ready to use.
- Use a clear structure: title, short introduction, ## sections, lists and tables where they help.
- Official documents (ariza, xat, bayonnoma, ma'lumotnoma, buyruq…) follow the usual structure used in Uzbekistan: addressee, title, body, date, signature lines. Leave placeholders like [F.I.Sh.], [sana], [manzil] for details the user did not give — never invent names, numbers, dates or document numbers.
- Use facts only from the numbered sources (cite them like [1]) and well-established general knowledge. Never invent statistics.

"""
    + WRITER_FORMAT
)

SPREADSHEET_SYSTEM = """You are EZO's spreadsheet builder. Reply with ONLY one JSON object:
{"title": str, "sheets": [{"name": str, "columns": [str, ...], "rows": [[cell, ...], ...]}]}
- Cells are strings or numbers (numbers as JSON numbers, without units or thousands separators; put units in the column name).
- Use ONLY data the user gave or that appears in the numbered sources. If the user wants a template (e.g. a budget or a plan), create the structure with clear column names and leave unknown values empty (null). Never invent figures.
- At most 500 rows. Write column names in {language}."""

DOCUMENT_INSTRUCTIONS = (
    "Role: document specialist. Use EZO's notes below:\n"
    "- If a file was created or edited, say briefly what it is (title, format, length) and, for "
    "edits, what changed (from the notes) — the file appears as a card under your message; do "
    "not paste the whole document and never invent links.\n"
    "- For comparisons and spreadsheet analysis use ONLY the facts and numbers in the notes; "
    "point out what stands out and what the user might check.\n"
    "- When a file's text is given as a source, answer from it and cite it.\n"
    "- If the notes say no file was found, ask the user to upload it with the paperclip button "
    "(or name it).\n"
    "- Be concise and practical."
)
NO_FILE_NOTE = (
    "The request refers to a file, but no matching uploaded file was found. Nothing was "
    "created. Ask the user to upload the file (paperclip button) or to name it."
)
OFFLINE_NOTE = (
    "No AI provider is connected, so EZO cannot write or rewrite documents now (format "
    "conversion and comparison still work). Nothing else was created."
)


@dataclass(frozen=True, slots=True)
class DocumentRequest:
    action: Action
    transform: Transform | None
    target_format: Format | None
    target_language: str | None
    wants_file: bool


_TARGET_AFTER = re.compile(r"^\w*\s*(ga|ka|qa|qil|ko'rinish|formatda|holida|sifatida|fayl qil)")
_TARGET_BEFORE = re.compile(r"(\b(to|into|as)|\bв|\bформат\w*)\s*$")


def requested_format(norm: str) -> Format | None:
    """The output format asked for. "Word faylni PDF ga aylantir" → pdf, "PDFni Word ga" →
    docx: a format marked as the target (-ga, qilib, to/into/as, в) wins, else the last
    one mentioned (the source is usually named first)."""
    mentions: list[tuple[int, int, Format]] = []
    for fmt, pattern in _FORMATS:
        mentions += [(m.start(), m.end(), fmt) for m in pattern.finditer(norm)]
    if not mentions:
        return None
    mentions.sort()
    for start, end, fmt in mentions:
        if _TARGET_AFTER.search(norm[end : end + 25]) or _TARGET_BEFORE.search(
            norm[max(0, start - 12) : start]
        ):
            return fmt
    return mentions[-1][2]


def classify_request(text: str) -> DocumentRequest:
    norm = normalize(text)
    fmt = requested_format(norm)
    target_language = next(
        (code for code, pattern in _LANGUAGES.items() if pattern.search(norm)), None
    )
    transform = next((name for name, pattern in _TRANSFORMS if pattern.search(norm)), None)
    wants_file = bool(_FILE_WANTED.search(norm)) or fmt is not None
    action: Action
    if _COMPARE.search(norm):
        action = "compare"
    elif (
        (_CONVERT.search(norm) or (_FORMAT_AS.search(norm) and refers_to_a_file(text)))
        and fmt is not None
        and transform is None
    ):
        action = "convert"
    elif _ANALYZE.search(norm) and _SHEET_NOUN.search(norm) and transform is None:
        action = "analyze"
    elif _SHEET_NOUN.search(norm) and _MAKE.search(norm) and transform is None:
        action = "spreadsheet"
    elif transform is not None:
        action = "transform"
    elif _MAKE.search(norm) and (wants_file or not refers_to_a_file(text)):
        action = "create"
    else:
        action = "answer"
    return DocumentRequest(action, transform, fmt, target_language, wants_file)


def parse_written(raw: str, fallback_title: str) -> tuple[str, str, str]:
    """(title, change summary, markdown) from a WRITER_FORMAT reply (tolerant of drift)."""
    title, changes, body = "", "", raw.strip()
    head, sep, rest = raw.partition("=====")
    if sep:
        body = rest.strip()
        for line in head.splitlines():
            key, _, value = line.partition(":")
            if key.strip().upper() == "TITLE":
                title = value.strip()
            elif key.strip().upper() == "CHANGES":
                changes = value.strip()
    if not title:
        first = next((ln for ln in body.splitlines() if ln.strip()), "")
        title = first.lstrip("# ").strip() if first.startswith("#") else fallback_title
    if body and not body.lstrip().startswith("# "):
        body = f"# {title}\n\n{body}"
    return title[:300] or fallback_title, changes[:500], body


@dataclass(slots=True)
class SourceText:
    """The text an action works on: an uploaded file or one of EZO's own documents."""

    title: str
    text: str
    document: DocumentRef | None = None
    artifact: Artifact | None = None
    table_summary: str = ""
    truncated: bool = False
    """True when `text` is only the beginning (see `DocumentAgent._full_text`)."""


class DocumentAgent(Agent):
    spec = AGENTS[Intent.DOCUMENT]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        request = classify_request(turn.text)
        return AgentPlan(
            route=self.spec.route,
            context_mode=self.spec.context_mode,
            instructions=DOCUMENT_INSTRUCTIONS,
            steps=(
                "classify_document_request",
                f"document:{request.action}",
                "compose_prompt",
                "generate",
            ),
        )

    # --- sources ---------------------------------------------------------------------------

    async def _read(
        self, gathered: Gathered, tools: ToolContext, ref: DocumentRef, limit: int
    ) -> SourceText | None:
        result = await call_tool(
            gathered,
            tools,
            "read_document",
            {"document_id": str(ref.document.id), "max_chars": max(limit, 1_000)},
        )
        if not result.ok:
            return None
        data = result.data
        source = SourceText(ref.document.title, str(data.get("text", "")), document=ref)
        source.table_summary = str(data.get("table_summary") or "")
        source.truncated = bool(data.get("truncated"))
        return source

    async def _full_text(self, ctx: GatherContext, source: SourceText) -> str:
        """The complete text of the source: the stored revision when the tool's read was cut."""
        if not source.truncated or source.document is None:
            return source.text
        document = source.document.document
        if document.current_revision_id is None:
            return source.text
        revision = await ctx.tools.session.get(DocumentRevision, document.current_revision_id)
        return revision.raw_text if revision is not None and revision.raw_text else source.text

    async def _artifact_text(self, tools: ToolContext) -> SourceText | None:
        """EZO's latest document in this conversation (its Markdown), for follow-up edits."""
        artifact = await latest_artifact(
            tools.session, tools.user_id, tools.conversation_id, ("document", "report")
        )
        if artifact is None:
            return None
        artifacts = tools.services.artifacts
        version = await artifacts.current_version(tools.session, artifact)
        if version is None:
            return None
        try:
            if version.filename.endswith((".md", ".txt")):
                raw = await artifacts.read(version)
            else:
                _, raw = await artifacts.read_export(version, "markdown")
        except ArtifactError:
            return None
        return SourceText(artifact.title, raw.decode("utf-8", "replace"), artifact=artifact)

    async def _sources_for(
        self, ctx: GatherContext, gathered: Gathered, count: int, limit: int
    ) -> list[SourceText]:
        tools = ctx.tools
        found: list[SourceText] = []
        attached = await attached_files(tools, ctx.turn.attachments)
        refs = (
            [DocumentRef(document, "attached") for document in attached][:count]
            if attached
            else await find_documents(
                tools.session, tools.user_id, tools.project_scope, ctx.turn.text, limit=count
            )
        )
        for ref in refs:
            read = await self._read(gathered, tools, ref, limit)
            if read is not None:
                found.append(read)
        if len(found) < count:
            own = await self._artifact_text(tools)
            if own is not None:
                found.append(own)
        return found[:count]

    async def _knowledge(self, ctx: GatherContext, gathered: Gathered) -> list[SourceRef]:
        tools = ctx.tools
        if not await has_searchable_documents(tools.session, tools.user_id, tools.project_scope):
            return []
        return await run_tool(
            gathered,
            tools,
            "knowledge_search",
            {"query": ctx.turn.text[:500], "limit": 5, "strict": True},
        )

    # --- actions ---------------------------------------------------------------------------

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        request = classify_request(ctx.turn.text)
        if (
            ctx.turn.attachments
            and request.target_format is not None
            and request.transform is None
            and request.action in ("create", "spreadsheet")
            and _FORMAT_AS.search(normalize(ctx.turn.text))
        ):
            # "Excel faylni PDF qilib ber" with a file attached: convert that file.
            request = replace(request, action="convert")
        # Deterministic EZO Office operations first: they need no model and no API key.
        planner_ok = request.action not in ("convert", "compare", "transform", "analyze")
        if await run_pdf_action(ctx, gathered, allow_planner=planner_ok):
            return gathered
        education = wants_education(ctx.turn.text)
        if education is not None and request.action not in ("convert", "compare"):
            # "Test tuz", "dars ishlanmasini tayyorla": teaching materials (also from a file).
            await self._educate(ctx, gathered, education)
            return gathered
        writing = wants_writing(normalize(ctx.turn.text))
        if writing is not None and request.transform is None:
            await self._write(ctx, gathered, writing)
            return gathered
        for action in (
            run_glossary_action,
            run_ocr_export_action,
            run_ocr_action,
            run_replace_action,
            run_tables_action,
            run_sheet_action,
            run_translit_action,
            run_inline_translation,
        ):
            if await action(ctx, gathered):
                return gathered
        gathered.tool_calls.append(
            {
                "tool": "classify_document_request",
                "ok": True,
                "error": None,
                "summary": f"action={request.action} transform={request.transform} format={request.target_format}",
            }
        )
        handler = {
            "convert": self._convert,
            "compare": self._compare,
            "analyze": self._analyze,
            "spreadsheet": self._spreadsheet,
            "transform": self._transform,
            "create": self._create,
            "answer": self._answer,
        }[request.action]
        try:
            await handler(ctx, gathered, request)
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("Document work failed: %s", exc)
            gathered.notes.append(
                "The AI provider failed while writing the document. Nothing was created. "
                "Say so and suggest trying again."
            )
        return gathered

    def _offline(self, ctx: GatherContext, gathered: Gathered) -> bool:
        if ctx.tools.services.router.is_offline:
            gathered.notes.append(OFFLINE_NOTE)
            return True
        return False

    async def _save_document(
        self,
        ctx: GatherContext,
        gathered: Gathered,
        *,
        title: str,
        markdown: str,
        fmt: Format,
        artifact: Artifact | None = None,
        change_summary: str = "",
        metadata: dict[str, Any] | None = None,
        references: list[dict[str, Any]] | None = None,
        provider: str | None = None,
        model: str | None = None,
        artifact_type: str = "document",
    ) -> dict[str, Any] | None:
        result = await call_tool(
            gathered,
            ctx.tools,
            "create_document",
            {
                "title": title,
                "markdown": markdown,
                "format": fmt,
                "artifact_type": artifact_type,
                "artifact_id": str(artifact.id) if artifact else None,
                "change_summary": change_summary,
                "metadata": metadata or {},
                "source_references": references or [],
                "provider": provider,
                "model": model,
            },
        )
        if not result.ok:
            gathered.notes.append(
                f"Creating the file failed ({result.error}). Nothing was saved; say so."
            )
            return None
        info: dict[str, Any] = result.data
        gathered.artifacts.append(info["artifact"])
        return info

    async def _convert(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        sources = await self._sources_for(ctx, gathered, 1, MAX_READ_CHARS)
        if not sources:
            gathered.notes.append(NO_FILE_NOTE)
            return
        source = sources[0]
        fmt = request.target_format or "docx"
        if fmt == "pdf" and await self._office_pdf(ctx, gathered, source):
            return
        info = await self._save_document(
            ctx,
            gathered,
            title=source.title,
            markdown=source.text,
            fmt=fmt,
            metadata={"action": "convert", **self._origin(source)},
            change_summary=f"Converted to {fmt.upper()}",
        )
        if info:
            layout_note = (
                " The text content was converted; the original file's page layout, images and "
                "fonts are not carried over."
                if source.document
                else ""
            )
            gathered.notes.append(
                f"Converted “{source.title}” to {fmt.upper()} ({info['words']} words; also available "
                f"as {', '.join(f.upper() for f in info['formats'][1:])}).{layout_note}"
            )

    async def _office_pdf(self, ctx: GatherContext, gathered: Gathered, source: SourceText) -> bool:
        """Word/Excel → PDF with its layout (LibreOffice). False: use the text conversion."""
        ref: dict[str, str] | None = None
        if source.document is not None:
            doc = source.document.document
            if doc.mime_type in (DOCX_MIME, XLSX_MIME):
                ref = {"kind": "document", "id": str(doc.id)}
        elif source.artifact is not None:
            version = await ctx.tools.services.artifacts.current_version(
                ctx.tools.session, source.artifact
            )
            if version is not None and version.filename.lower().endswith((".docx", ".xlsx")):
                ref = {"kind": "artifact", "id": str(source.artifact.id)}
        if ref is None:
            return False
        result = await call_tool(gathered, ctx.tools, "office_pdf", {"input": ref})
        if not result.ok:
            if (result.data or {}).get("error_kind") == "unavailable":
                gathered.notes.append(
                    "LibreOffice is not installed on this server, so the PDF below is made from "
                    "the file's text: its page layout, tables' look, images and fonts are not "
                    "carried over. Say this clearly."
                )
                return False
            gathered.notes.append(f"The PDF could not be made: {result.error} Say so plainly.")
            return True
        data = result.data or {}
        gathered.artifacts.extend(data.get("artifacts", []))
        gathered.notes.append(
            f"Converted “{source.title}” to PDF with LibreOffice from the original "
            f"{str(data.get('kind', '')).upper()} file, keeping its layout (styles, tables, "
            f"headers, page setup): {data.get('pages')} page(s), reopened and checked. Fonts "
            "the server does not have are replaced by similar ones. The original is unchanged."
        )
        return True

    async def _compare(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        sources = await self._sources_for(ctx, gathered, 2, 200_000)
        if len(sources) < 2:
            gathered.notes.append(
                "Comparing needs two files, but fewer were found. Ask the user to upload both files "
                "or name them."
            )
            return
        first, second = sources[0], sources[1]
        comparison = compare_texts(second.text, first.text)
        gathered.tool_calls.append(
            {
                "tool": "compare_documents",
                "ok": True,
                "error": None,
                "summary": comparison.summary(),
            }
        )
        diff = comparison.to_markdown(limit=30)
        pdf_facts = await self._compare_pdfs(ctx, second, first)
        gathered.notes.append(
            f"Comparison of “{second.title}” (original) and “{first.title}” (newer): "
            f"{comparison.summary()}."
            + (f"\nPDF page-level comparison (computed by EZO): {pdf_facts}" if pdf_facts else "")
            + f"\nDifferences (paragraph level):\n{diff[:8_000]}"
        )
        if request.wants_file:
            pages = f"{pdf_facts}\n\n" if pdf_facts else ""
            markdown = (
                f"# {first.title} — {second.title}\n\n{comparison.summary()}\n\n{pages}{diff}"
            )
            await self._save_document(
                ctx,
                gathered,
                title=f"Taqqoslash: {first.title}"[:300],
                markdown=markdown,
                fmt=request.target_format or "docx",
                artifact_type="report",
                metadata={"action": "compare", "comparison": comparison.summary()},
            )

    async def _compare_pdfs(
        self, ctx: GatherContext, original: SourceText, newer: SourceText
    ) -> str:
        """Page counts, changed pages and metadata differences when both files are PDFs."""
        docs = [s.document.document for s in (original, newer) if s.document is not None]
        if len(docs) != 2 or any(
            d.mime_type != "application/pdf" or not d.storage_key for d in docs
        ):
            return ""
        storage = ctx.tools.services.storage
        try:
            a = await storage.get(docs[0].storage_key or "")
            b = await storage.get(docs[1].storage_key or "")
            result = await asyncio.to_thread(pdf_engine.compare_pdfs, a, b)
        except (PdfError, StorageError):
            return ""
        return result.summary()

    async def _analyze(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        sources = await self._sources_for(ctx, gathered, 1, ANSWER_CHARS)
        if not sources:
            gathered.notes.append(NO_FILE_NOTE)
            return
        source = sources[0]
        ref = source.document
        if ref is None:
            gathered.notes.append(NO_FILE_NOTE)
            return
        gathered.sources = [document_source(ref.document, source.text, ANSWER_CHARS)]
        if not source.table_summary:
            gathered.notes.append(
                f"“{source.title}” is not a spreadsheet EZO can compute statistics for; answer from "
                "its text (cited) and say that no exact statistics were computed."
            )
            return
        gathered.notes.append(
            "Spreadsheet facts computed by EZO (exact; use these numbers, do not recompute):\n"
            + source.table_summary[:6_000]
        )

    async def _spreadsheet(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        if self._offline(ctx, gathered):
            return
        knowledge = await self._knowledge(ctx, gathered)
        number_sources(knowledge)
        tools = ctx.tools
        if tools.on_activity is not None:
            tools.on_activity("creating")
        completion = await complete(
            tools.services.router,
            "chat",
            system=SPREADSHEET_SYSTEM.replace(
                "{language}", LANGUAGE_NAMES.get(ctx.turn.language, "Uzbek")
            ),
            messages=[ChatMessage("user", f"{ctx.turn.text}\n\n{sources_block(knowledge)}")],
            max_output_tokens=12_000,
            language=ctx.turn.language,
        )
        gathered.tool_calls.append(
            completion.trace("plan_spreadsheet", f"{len(completion.text)} chars")
        )
        data = extract_json(completion.text) or {}
        sheets: list[dict[str, Any]] = [
            {
                "name": str(s.get("name", "Sheet1"))[:100],
                "columns": [str(c)[:200] for c in s.get("columns", [])][:100],
                "rows": [
                    [c if isinstance(c, int | float | str) or c is None else str(c) for c in row][
                        :100
                    ]
                    for row in s.get("rows", [])[:SPREADSHEET_ROWS]
                    if isinstance(row, list)
                ],
            }
            for s in data.get("sheets", [])
            if isinstance(s, dict) and s.get("columns")
        ][:20]
        gathered.sources = knowledge
        if not sheets:
            gathered.notes.append(
                "The spreadsheet could not be built (no valid table came back). Nothing was created; say so."
            )
            return
        result = await call_tool(
            gathered,
            tools,
            "create_spreadsheet",
            {
                "title": str(data.get("title") or "Jadval")[:300],
                "sheets": sheets,
                "format": "csv" if request.target_format == "txt" else "xlsx",
                "provider": completion.provider,
                "model": completion.model,
            },
        )
        if not result.ok:
            gathered.notes.append(f"Creating the spreadsheet failed ({result.error}); say so.")
            return
        gathered.artifacts.append(result.data["artifact"])
        columns = ", ".join(sheets[0]["columns"][:12])
        gathered.notes.append(
            f"Created spreadsheet “{result.data['artifact']['title']}”: {len(sheets)} sheet(s), "
            f"{result.data['rows']} rows; columns: {columns}. Empty cells mean the value was not given."
        )

    async def _transform(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        sources = await self._sources_for(ctx, gathered, 1, MAX_READ_CHARS)
        if not sources:
            gathered.notes.append(NO_FILE_NOTE)
            return
        source = sources[0]
        full = await self._full_text(ctx, source)
        transform = request.transform or "rewrite"
        if transform == "summarize" and not request.wants_file and source.document is not None:
            if len(full) <= ANSWER_CHARS:
                # A summary in the chat: the model reads the file as a cited source.
                gathered.sources = [document_source(source.document.document, full, ANSWER_CHARS)]
                return
            if self._offline(ctx, gathered):
                return
            await self._summarize_long_in_chat(ctx, gathered, source, full)
            return
        plan: TranslationPlan | None = None
        terms: list[glossary.Term] = []
        if transform == "translate":
            plan = translation_plan(ctx.turn.text, full, ctx.turn.language)
            if base(plan.source) == base(plan.target):
                gathered.notes.append(
                    f"“{source.title}” is already in {NAMES.get(plan.source, plan.source)}, the "
                    "language asked for. Nothing was translated; say so and ask which language "
                    "they want."
                )
                return
        if self._offline(ctx, gathered):
            return
        if plan is not None:
            terms = glossary.relevant(
                await load_glossary(ctx.tools, plan.source, plan.target), full, plan.source
            )
        if transform != "summarize" and request.target_format in (None, "docx"):
            docx = await find_docx(ctx, source.document.document if source.document else None)
            if docx is not None:
                target = (
                    plan.target
                    if plan
                    else request.target_language or ("en" if ctx.turn.language == "uz" else "uz")
                )
                label = {
                    "translate": f"Translated to {NAMES.get(target, target)}",
                    "proofread": "Proofread",
                    "rewrite": "Rewritten",
                    "formalize": "Formal style",
                }[transform]
                await transform_docx(
                    ctx,
                    gathered,
                    docx,
                    transform=transform,
                    task=self._task(transform, target, plan, terms),
                    label=label,
                    target_language=target if transform == "translate" else None,
                    review=docx_review(plan, terms, docx.title) if plan else None,
                )
                return
        target = (
            plan.target
            if plan
            else request.target_language or ("en" if ctx.turn.language == "uz" else "uz")
        )
        task = self._task(transform, target, plan, terms)
        if len(full) > SOURCE_CHARS:
            await self._transform_long(
                ctx, gathered, request, source, full, transform, task, target, plan, terms
            )
            return
        text = full
        partial = False
        tools = ctx.tools
        if tools.on_activity is not None:
            tools.on_activity("creating")
        completion = await complete(
            tools.services.router,
            "chat",
            system=TRANSFORM_SYSTEM.replace("{task}", task),
            messages=[
                ChatMessage(
                    "user",
                    f"User's request: {ctx.turn.text}\n\nDocument “{source.title}”:\n\n{text}",
                )
            ],
            max_output_tokens=min(32_000, int(len(text) / 2.5) + 2_000),
            language=ctx.turn.language,
        )
        gathered.tool_calls.append(
            completion.trace(f"{transform}_document", f"{len(completion.text)} chars")
        )
        title, changes, markdown = parse_written(completion.text, source.title)
        if not markdown.strip():
            gathered.notes.append("The edited document came back empty. Nothing was saved; say so.")
            return
        extra: dict[str, Any] = {}
        extra_lines: list[str] = []
        if plan is not None:
            markdown, extra, extra_lines = await finish_markdown_translation(
                ctx, gathered, plan, terms, text, markdown, title
            )
        comparison = compare_texts(text, markdown)
        metadata = {
            "action": transform,
            **self._origin(source),
            "comparison": comparison.summary(),
            "partial": partial,
            **({"target_language": target} if transform == "translate" else {}),
            **extra,
        }
        summary = (
            changes
            or {
                "summarize": "Summarized",
                "translate": f"Translated to {NAMES.get(target, target)}",
                "proofread": "Proofread",
                "rewrite": "Rewritten",
                "formalize": "Formal style",
            }[transform]
        )
        info = await self._save_document(
            ctx,
            gathered,
            title=title,
            markdown=markdown,
            fmt=request.target_format or "docx",
            artifact=source.artifact,  # EZO's own document → new version; an upload → new artifact
            change_summary=summary,
            metadata=metadata,
            provider=completion.provider,
            model=completion.model,
        )
        if info is None:
            return
        where = (
            f"a new version (v{info['artifact']['version']}) of “{source.title}”"
            if source.artifact is not None
            else f"a new document derived from “{source.title}” (the original file is unchanged)"
        )
        gathered.notes.append(
            f"Saved as {where}: “{title}”, {info['words']} words, formats {', '.join(info['formats'])}.\n"
            f"Change summary: {summary}.\nDifference from the original: {comparison.summary()}."
            + (
                f"\nOnly the first {SOURCE_CHARS:,} characters were processed because the file is long — say so."
                if partial
                else ""
            )
            + (
                "\nIf the change summary mentions [?], tell the user which parts were unclear."
                if "[?]" in markdown
                else ""
            )
            + ("\n" + "\n".join(extra_lines) if extra_lines else "")
        )

    @staticmethod
    def _task(
        transform: str, target: str, plan: TranslationPlan | None, terms: list[glossary.Term]
    ) -> str:
        if plan is None:
            return TRANSFORM_TASKS[transform].replace(
                "{target}", LANGUAGE_NAMES.get(target, target)
            )
        model_target = "uz" if target == "uz-cyrl" else target
        block = glossary.prompt_block(terms, model_target)
        return (
            TRANSFORM_TASKS["translate"].replace("{target}", NAMES[model_target])
            + f" Source language: {NAMES.get(plan.source, plan.source)}. "
            + DOMAIN_RULES.get(plan.domain, DOMAIN_RULES["general"])
            + (f"\n{block}" if block else "")
        )

    async def _summarize_long_in_chat(
        self, ctx: GatherContext, gathered: Gathered, source: SourceText, full: str
    ) -> None:
        language = LANGUAGE_NAMES.get(ctx.turn.language, "Uzbek")
        try:
            summary = await summarize_long(ctx, gathered, source.title, full, language)
        except TooLongError as exc:
            gathered.notes.append(too_long_note(source.title, exc.chars))
            return
        if summary is None:
            return
        outline_titles = outline(full, 25)
        gathered.notes.append(
            f"EZO read ALL of “{source.title}” ({summary.chars:,} characters) in "
            f"{summary.parts} parts that follow its sections"
            + (f" ({summary.reused} part(s) reused from earlier work)" if summary.reused else "")
            + ", summarised each part and combined them. Present this summary (you may shorten "
            "it to fit the reply, but do not add facts) and say it covers the whole document."
            + (f"\nThe document's sections: {'; '.join(outline_titles)}" if outline_titles else "")
            + f"\nSUMMARY:\n{summary.text}"
        )

    async def _transform_long(
        self,
        ctx: GatherContext,
        gathered: Gathered,
        request: DocumentRequest,
        source: SourceText,
        full: str,
        transform: str,
        task: str,
        target: str,
        plan: TranslationPlan | None = None,
        terms: list[glossary.Term] | None = None,
    ) -> None:
        language = LANGUAGE_NAMES.get(request.target_language or ctx.turn.language, "Uzbek")
        try:
            if transform == "summarize":
                summary = await summarize_long(ctx, gathered, source.title, full, language)
                if summary is None:
                    return
                title = f"{source.title} — summary"
                markdown = f"# {title}\n\n{summary.text}"
                parts, reused = summary.parts, summary.reused
                provider, model = summary.provider, summary.model
            else:
                key = f"{transform}:{target if transform == 'translate' else language}"
                done = await transform_long(
                    ctx, gathered, source.title, full, transform=transform, task=task, task_key=key
                )
                if done is None:
                    return
                body, run, parts = done
                reused, provider, model = run.reused, run.provider, run.model
                suffix = f" ({target})" if transform == "translate" else ""
                title = f"{source.title}{suffix}"
                markdown = body if body.lstrip().startswith("# ") else f"# {title}\n\n{body}"
        except TooLongError as exc:
            gathered.notes.append(too_long_note(source.title, exc.chars))
            return
        extra: dict[str, Any] = {}
        extra_lines: list[str] = []
        if plan is not None:
            markdown, extra, extra_lines = await finish_markdown_translation(
                ctx, gathered, plan, terms or [], full, markdown, title
            )
        summary_text = {
            "summarize": "Summarized (whole document)",
            "translate": f"Translated to {NAMES.get(target, target)} (whole document)",
            "proofread": "Proofread (whole document)",
            "rewrite": "Rewritten (whole document)",
            "formalize": "Formal style (whole document)",
        }[transform]
        info = await self._save_document(
            ctx,
            gathered,
            title=title,
            markdown=markdown,
            fmt=request.target_format or "docx",
            artifact=source.artifact,
            change_summary=summary_text,
            metadata={
                "action": transform,
                **self._origin(source),
                "long_document": {
                    "chars": len(full),
                    "parts": parts,
                    "reused_parts": reused,
                    "method": "map-reduce summary" if transform == "summarize" else "part by part",
                },
                "partial": False,
                **({"target_language": target} if transform == "translate" else {}),
                **extra,
            },
            provider=provider,
            model=model,
        )
        if info is None:
            return
        gathered.notes.append(
            f"Processed ALL of “{source.title}” ({len(full):,} characters) in {parts} parts that "
            f"follow its sections{f' ({reused} reused from earlier work)' if reused else ''}; "
            f"saved as “{title}” ({info['words']} words, formats {', '.join(info['formats'])}). "
            "The original file is unchanged. Say that the whole document was covered."
            + ("\n" + "\n".join(extra_lines) if extra_lines else "")
        )

    async def _file_sources(self, ctx: GatherContext, gathered: Gathered) -> list[SourceRef]:
        """Attached files (up to three) as numbered sources, else the knowledge base."""
        tools = ctx.tools
        sources: list[SourceRef] = []
        for document in (await attached_files(tools, ctx.turn.attachments))[:3]:
            read = await self._read(
                gathered, tools, DocumentRef(document, "attached"), ANSWER_CHARS
            )
            if read is not None and read.text.strip():
                sources.append(document_source(document, read.text, ANSWER_CHARS))
        if not sources and not tools.services.router.is_offline:
            sources = await self._knowledge(ctx, gathered)
        number_sources(sources)
        return sources

    async def _educate(self, ctx: GatherContext, gathered: Gathered, kind: Kind) -> None:
        """Teaching and study materials, based on the user's files when attached."""
        await make_material(ctx, gathered, kind, await self._file_sources(ctx, gathered))

    async def _write(self, ctx: GatherContext, gathered: Gathered, doc: DocType) -> None:
        """Professional writing: facts from attached files (or the knowledge base) only."""
        await write_document(ctx, gathered, doc, await self._file_sources(ctx, gathered))

    async def _create(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        if self._offline(ctx, gathered):
            return
        knowledge = await self._knowledge(ctx, gathered)
        number_sources(knowledge)
        tools = ctx.tools
        if tools.on_activity is not None:
            tools.on_activity("creating")
        language = LANGUAGE_NAMES.get(request.target_language or ctx.turn.language, "Uzbek")
        completion = await complete(
            tools.services.router,
            "reasoning",
            system=CREATE_SYSTEM.replace("{language}", language),
            messages=[ChatMessage("user", f"{ctx.turn.text}\n\n{sources_block(knowledge)}")],
            max_output_tokens=12_000,
            language=ctx.turn.language,
        )
        gathered.tool_calls.append(
            completion.trace("write_document", f"{len(completion.text)} chars")
        )
        gathered.sources = knowledge
        title, _, markdown = parse_written(completion.text, "Hujjat")
        if not markdown.strip():
            gathered.notes.append("The document came back empty. Nothing was saved; say so.")
            return
        info = await self._save_document(
            ctx,
            gathered,
            title=title,
            markdown=markdown,
            fmt=request.target_format or "docx",
            metadata={"action": "create"},
            references=[s.to_metadata() for s in knowledge],
            provider=completion.provider,
            model=completion.model,
            artifact_type="report"
            if re.search(r"\b(hisobot|report|отч[её]т)", normalize(ctx.turn.text))
            else "document",
        )
        if info:
            placeholders = sorted(
                set(re.findall(r"\[[^\]\[]{2,40}\]", markdown)) - {f"[{s.n}]" for s in knowledge}
            )
            gathered.notes.append(
                f"Created “{title}”: {info['words']} words, formats {', '.join(info['formats'])}."
                + (
                    f" Placeholders the user must fill in: {', '.join(placeholders[:12])}."
                    if placeholders
                    else ""
                )
            )

    async def _answer(
        self, ctx: GatherContext, gathered: Gathered, request: DocumentRequest
    ) -> None:
        tools = ctx.tools
        attached = await attached_files(tools, ctx.turn.attachments)
        refs = (
            [DocumentRef(d, "attached") for d in attached]
            if attached
            else await find_documents(
                tools.session, tools.user_id, tools.project_scope, ctx.turn.text
            )
        )
        if refs:
            read = await self._read(gathered, tools, refs[0], ANSWER_CHARS)
            if read is not None:
                if not read.truncated:
                    gathered.sources = [document_source(refs[0].document, read.text, ANSWER_CHARS)]
                    return
                # A long file: search all of it and answer from the most relevant passages.
                found = await answer_sources(ctx, refs[0].document, ctx.turn.text)
                gathered.sources = found
                gathered.notes.append(
                    f"“{read.title}” is long; EZO searched the WHOLE file and gives the "
                    f"{len(found)} most relevant passages (with their pages/sections). Answer "
                    "only from them and cite them; if they do not contain the answer, say that "
                    "the answer was not found in the file — do not guess."
                )
                return
        gathered.sources = await self._knowledge(ctx, gathered)
        if not gathered.sources and refers_to_a_file(ctx.turn.text):
            gathered.notes.append(NO_FILE_NOTE)

    @staticmethod
    def _origin(source: SourceText) -> dict[str, Any]:
        if source.document is not None:
            doc = source.document.document
            return {
                "derived_from": {
                    "kind": "knowledge_document",
                    "id": str(doc.id),
                    "title": doc.title,
                }
            }
        if source.artifact is not None:
            return {
                "derived_from": {
                    "kind": "artifact",
                    "id": str(source.artifact.id),
                    "title": source.artifact.title,
                }
            }
        return {}
