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

import logging
import re
from dataclasses import dataclass
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
from ezo_api.agents.llm import complete, extract_json, sources_block
from ezo_api.agents.office import attached_files, run_ocr_action, run_pdf_action
from ezo_api.agents.references import (
    DocumentRef,
    document_source,
    find_documents,
    latest_artifact,
    refers_to_a_file,
)
from ezo_api.artifacts.service import ArtifactError
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.models import Artifact
from ezo_api.documents.compare import compare_texts
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.knowledge.retrieval.sources import SourceRef, number_sources
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext
from ezo_api.tools.document_tools import MAX_READ_CHARS

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
_SHEET_NOUN = re.compile(r"\b(excel|xlsx|spreadsheet|jadval|таблиц|эксель)")
_MAKE = re.compile(
    r"\b(yarat|tuz|tayyorla|qil|yoz|create|make|build|draft|write|prepare|generate|созда|сделай|составь|подготов|напиши)"
)
_ANALYZE = re.compile(
    r"\b(tahlil|analy|анализ|statistik|o'rtacha|jami|sum|average|total|итог|средн|insight)"
)
_FILE_WANTED = re.compile(
    r"\b(fayl|file|файл|docx|word|pdf|hujjat qilib|yuklab|download|скача|документ(ом)? )"
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


def requested_format(norm: str) -> Format | None:
    for fmt, pattern in _FORMATS:
        if pattern.search(norm):
            return fmt
    return None


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
    elif _CONVERT.search(norm) and fmt is not None and transform is None:
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
        return source

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
        # Deterministic EZO Office operations first: they need no model and no API key.
        planner_ok = request.action not in ("convert", "compare", "transform", "analyze")
        if await run_pdf_action(ctx, gathered, allow_planner=planner_ok):
            return gathered
        for action in (
            run_ocr_export_action,
            run_ocr_action,
            run_replace_action,
            run_tables_action,
            run_sheet_action,
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
        gathered.notes.append(
            f"Comparison of “{second.title}” (original) and “{first.title}” (newer): "
            f"{comparison.summary()}.\nDifferences (paragraph level):\n{diff[:8_000]}"
        )
        if request.wants_file:
            markdown = f"# {first.title} — {second.title}\n\n{comparison.summary()}\n\n{diff}"
            await self._save_document(
                ctx,
                gathered,
                title=f"Taqqoslash: {first.title}"[:300],
                markdown=markdown,
                fmt=request.target_format or "docx",
                artifact_type="report",
                metadata={"action": "compare", "comparison": comparison.summary()},
            )

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
        sources = await self._sources_for(ctx, gathered, 1, SOURCE_CHARS)
        if not sources:
            gathered.notes.append(NO_FILE_NOTE)
            return
        source = sources[0]
        transform = request.transform or "rewrite"
        if transform == "summarize" and not request.wants_file and source.document is not None:
            # A summary in the chat: the model reads the file as a cited source.
            gathered.sources = [
                document_source(source.document.document, source.text, ANSWER_CHARS)
            ]
            if len(source.text) > ANSWER_CHARS:
                gathered.notes.append(
                    f"Only the first {ANSWER_CHARS:,} characters of “{source.title}” fit; say the "
                    "summary covers the beginning of the file."
                )
            return
        if self._offline(ctx, gathered):
            return
        if transform != "summarize" and request.target_format in (None, "docx"):
            docx = await find_docx(ctx, source.document.document if source.document else None)
            if docx is not None:
                target = request.target_language or ("en" if ctx.turn.language == "uz" else "uz")
                label = {
                    "translate": f"Translated to {LANGUAGE_NAMES.get(target, target)}",
                    "proofread": "Proofread",
                    "rewrite": "Rewritten",
                    "formalize": "Formal style",
                }[transform]
                task = TRANSFORM_TASKS[transform].replace(
                    "{target}", LANGUAGE_NAMES.get(target, target)
                )
                await transform_docx(
                    ctx,
                    gathered,
                    docx,
                    transform=transform,
                    task=task,
                    label=label,
                    target_language=target if transform == "translate" else None,
                )
                return
        text = source.text[:SOURCE_CHARS]
        partial = len(source.text) > SOURCE_CHARS
        target = request.target_language or ("en" if ctx.turn.language == "uz" else "uz")
        task = TRANSFORM_TASKS[transform].replace("{target}", LANGUAGE_NAMES.get(target, target))
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
        comparison = compare_texts(text, markdown)
        metadata = {
            "action": transform,
            **self._origin(source),
            "comparison": comparison.summary(),
            "partial": partial,
            **({"target_language": target} if transform == "translate" else {}),
        }
        summary = (
            changes
            or {
                "summarize": "Summarized",
                "translate": f"Translated to {LANGUAGE_NAMES.get(target, target)}",
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
        )

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
        refs = await find_documents(
            tools.session, tools.user_id, tools.project_scope, ctx.turn.text
        )
        if refs:
            read = await self._read(gathered, tools, refs[0], ANSWER_CHARS)
            if read is not None:
                gathered.sources = [document_source(refs[0].document, read.text, ANSWER_CHARS)]
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
