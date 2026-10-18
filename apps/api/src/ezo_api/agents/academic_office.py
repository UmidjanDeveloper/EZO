# ruff: noqa: E501  (note texts are kept on readable lines)
"""Academic research assistance in chat (Stage D).

- "Shu mavzu bo'yicha ilmiy manbalarni top, tadqiqot rejasini tuz": EZO searches OpenAlex
  for real works (and uses attached files), the model writes the plan citing only those
  works as [n], EZO checks the citations and writes the reference list itself. Without an
  AI model EZO still returns the literature list (search needs no model).
- "Shu adabiyotlarni APA formatiga o'tkaz: …": the model only splits the given references
  into fields; every field must appear in the user's text (otherwise it is dropped and
  reported), and EZO formats them.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ezo_api.academic.citations import (
    STYLE_NAMES,
    Reference,
    Style,
    clean_doi,
    format_list,
    in_text,
    style_from,
)
from ezo_api.academic.plan import (
    PLAN_SYSTEM,
    QUERY_SYSTEM,
    Plan,
    check_plan,
    parse_plan,
    remove_bad_citations,
)
from ezo_api.academic.scholar import ScholarError, Work
from ezo_api.agents.base import GatherContext, Gathered, call_tool
from ezo_api.agents.llm import complete, extract_json
from ezo_api.core.text import normalize
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.translation.requests import inline_text
from ezo_api.writing.service import LANGUAGE_NAMES
from ezo_api.writing.style import options_from as style_options

ROUTE = "chat"
MAX_WORKS = 15
_COMMAND_WORDS = re.compile(
    r"\b(shu|mavzu\w*|bo'yicha|ilmiy|manba\w*|adabiyot\w*|top\w*|tadqiqot|reja\w*|tuz|va|"
    r"himoya\w*|tayyorla\w*|yordam|ber|find|research|papers?|on|about|plan|the|a|for|"
    r"найди|научн\w*|источник\w*|план|исследовани\w*|по|составь|и)\b"
)
_CITATION = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
_PLAN = re.compile(r"\b(reja\w*|plan\w*|outline|proposal|taklif\w*|план\w*|структур\w*)")


def _language(ctx: GatherContext) -> str:
    language = style_options(ctx.turn.text).language or {"ru": "ru", "en": "en"}.get(
        ctx.turn.language, "uz"
    )
    return "uz" if language == "uz-cyrl" else language


def _heuristic_query(text: str) -> str:
    words = _COMMAND_WORDS.sub(" ", normalize(text))
    return " ".join(w for w in re.split(r"[^\w'-]+", words) if len(w) > 2)[:200]


def _file_reference(source: SourceRef) -> Reference:
    return Reference(title=source.title, kind="report", url=source.url or "")


def _cite(text: str, references: list[Reference], style: Style) -> str:
    """[n] → the style's in-text citation (numeric styles keep [n])."""
    if style in ("ieee", "gost"):
        return text

    def replace(match: re.Match[str]) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        parts = [
            in_text(references[n - 1], style, n).strip("()")
            for n in numbers
            if 1 <= n <= len(references)
        ]
        return f"({'; '.join(parts)})" if parts else ""

    return _CITATION.sub(replace, text)


def _markdown(
    plan: Plan | None, references: list[Reference], works: list[Work], style: Style, topic: str
) -> str:
    title = (plan.title if plan else "") or f"Adabiyotlar: {topic}"
    lines = [f"# {title}", ""]
    if plan is not None:

        def fix(text: str) -> str:
            return _cite(remove_bad_citations(text, len(references)), references, style)

        sections: list[tuple[str, list[str]]] = [
            ("Tadqiqot savollari", plan.research_questions),
            ("Maqsad va vazifalar", plan.objectives),
            ("Farazlar (tekshirilishi kerak)", plan.hypotheses),
        ]
        for heading, items in sections:
            if items:
                lines += [f"## {heading}", "", *[f"- {fix(i)}" for i in items], ""]
        method = plan.methodology
        method_lines = [
            f"**{label}:** {fix(value)}"
            for label, value in (
                ("Dizayn", method.design),
                ("Ma'lumotlar", method.data),
                ("Tanlanma", method.sample),
                ("Etika", method.ethics),
            )
            if value
        ] + [f"- {fix(m)}" for m in method.methods]
        if method_lines:
            lines += ["## Metodologiya", "", *method_lines, ""]
        if plan.literature_review:
            lines += ["## Adabiyotlar sharhi", ""]
            for theme in plan.literature_review:
                lines += ([f"### {theme.theme}", ""] if theme.theme else []) + [fix(theme.text), ""]
        if plan.timeline:
            lines += ["## Ish rejasi", "", "| Davr | Vazifa |", "|---|---|"]
            lines += [f"| {p.period} | {p.task} |" for p in plan.timeline] + [""]
        if plan.limitations:
            lines += ["## Cheklovlar", "", *[f"- {fix(x)}" for x in plan.limitations], ""]
        if plan.defense_questions:
            lines += ["## Himoyaga tayyorgarlik: ehtimoliy savollar", ""]
            lines += [
                f"{i}. **{q.question}** — {q.hint}"
                for i, q in enumerate(plan.defense_questions, start=1)
            ] + [""]
        if plan.next_steps:
            lines += ["## Keyingi qadamlar", "", *[f"- {fix(x)}" for x in plan.next_steps], ""]
    lines += [f"## Foydalanilgan adabiyotlar ({STYLE_NAMES[style]})", ""]
    if references:
        lines += [f"- {entry}" for entry in format_list(references, style)] + [""]
        lines.append(
            "*Ro'yxatni EZO OpenAlex va sizning fayllaringiz ma'lumotlaridan tuzdi. Iqtibos keltirishdan oldin har bir manbani o'qing.*"
        )
    else:
        lines.append("*Manba topilmadi.*")
    return "\n".join(lines).strip() + "\n"


def _sheet(references: list[Reference], works: list[Work]) -> dict[str, Any]:
    extra = {w.reference.title: w for w in works}
    rows = []
    for number, ref in enumerate(references, start=1):
        work = extra.get(ref.title)
        rows.append(
            [
                number,
                "; ".join(ref.authors),
                ref.year,
                ref.title,
                ref.container,
                ref.doi,
                ref.url,
                work.cited_by if work else None,
                work.open_access_url if work else "",
                ", ".join(ref.missing()),
            ]
        )
    return {
        "name": "Adabiyotlar",
        "columns": [
            "№",
            "Mualliflar",
            "Yil",
            "Sarlavha",
            "Jurnal / manba",
            "DOI",
            "Havola",
            "Iqtiboslar",
            "Ochiq matn",
            "Yetishmaydi",
        ],
        "rows": rows,
    }


async def run_research_plan(ctx: GatherContext, gathered: Gathered, files: list[SourceRef]) -> None:
    tools = ctx.tools
    router = tools.services.router
    language = _language(ctx)
    style: Style = style_from(normalize(ctx.turn.text)) or "apa"
    topic = _heuristic_query(ctx.turn.text)
    queries = [topic] if topic else []
    from_year: int | None = None
    provider = model = None
    if not router.is_offline:
        try:
            completion = await complete(
                router,
                ROUTE,
                system=QUERY_SYSTEM,
                messages=[ChatMessage("user", ctx.turn.text)],
                max_output_tokens=400,
            )
            gathered.tool_calls.append(completion.trace("research_queries", "queries"))
            data = extract_json(completion.text) or {}
            topic = str(data.get("topic") or topic)[:300]
            queries = [str(q)[:200] for q in data.get("queries") or [] if str(q).strip()][
                :2
            ] or queries
            year = data.get("from_year")
            from_year = year if isinstance(year, int) and 1900 < year < 2100 else None
        except (AllProvidersFailedError, StreamInterruptedError):
            pass
    works: list[Work] = []
    search_note = ""
    scholar = tools.services.scholar
    if scholar is None:
        search_note = "Scholarly search (OpenAlex) is turned off (EZO_SCHOLAR_PROVIDER=none), so no literature was searched."
    elif queries:
        seen: set[str] = set()
        try:
            for query in queries:
                for work in await scholar.search(query, 10, from_year):
                    key = work.reference.doi or normalize(work.reference.title)
                    if key not in seen:
                        seen.add(key)
                        works.append(work)
            gathered.tool_calls.append(
                {
                    "tool": "scholar_search",
                    "ok": True,
                    "summary": f"{len(works)} works for {queries}",
                    "error": None,
                }
            )
        except ScholarError as exc:
            search_note = (
                f"The literature search failed: {exc.message} No works were invented to replace it."
            )
            gathered.tool_calls.append(
                {"tool": "scholar_search", "ok": False, "summary": "", "error": exc.message}
            )
    works = works[:MAX_WORKS]
    references = [w.reference for w in works] + [_file_reference(s) for s in files]
    plan: Plan | None = None
    report = check_plan(Plan(), 0)
    want_plan = bool(_PLAN.search(normalize(ctx.turn.text)))
    if want_plan and not router.is_offline:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        blocks = []
        for number, ref in enumerate(references, start=1):
            found = works[number - 1] if number <= len(works) else None
            summary = (
                found.abstract
                if found
                else next((s.excerpt[:1500] for s in files if s.title == ref.title), "")
            )
            blocks.append(
                f'<work n="{number}">{ref.title} — {", ".join(ref.authors[:3]) or "author unknown"} ({ref.year or "n.d."}), {ref.container}\n{summary}</work>'
            )
        try:
            completion = await complete(
                router,
                ROUTE,
                system=PLAN_SYSTEM.format(
                    language=LANGUAGE_NAMES.get(language, language),
                    periods="months unless the user gave weeks",
                ),
                messages=[
                    ChatMessage(
                        "user",
                        f"User's request:\n{ctx.turn.text}\n\nTopic: {topic}\n\nWorks:\n"
                        + ("\n\n".join(blocks) or "(none found)"),
                    )
                ],
                max_output_tokens=8_000,
                language=ctx.turn.language,
            )
            gathered.tool_calls.append(
                completion.trace("research_plan", f"{len(completion.text)} chars")
            )
            provider, model = completion.provider, completion.model
            plan = parse_plan(extract_json(completion.text))
            if plan is None:
                gathered.notes.append(
                    "The model's plan could not be read; only the literature list was saved."
                )
            else:
                report = check_plan(plan, len(references))
        except (AllProvidersFailedError, StreamInterruptedError):
            gathered.notes.append(
                "The AI provider failed while writing the plan; only the literature list was saved."
            )
    if plan is None and not references:
        gathered.notes.append(
            (search_note or "No literature was found for this topic.")
            + " Nothing was saved; say so and suggest other keywords."
        )
        return
    markdown = _markdown(plan, references, works, style, topic)
    metadata = {
        "action": "research_plan" if plan else "literature_list",
        "topic": topic,
        "queries": queries,
        "style": style,
        "works": [
            {"openalex_id": w.openalex_id, "doi": w.reference.doi, "title": w.reference.title}
            for w in works
        ],
        "files": [s.title for s in files],
        "check": report.summary(),
    }
    title = (plan.title if plan and plan.title else f"Adabiyotlar: {topic}")[:200]
    document = await call_tool(
        gathered,
        tools,
        "create_document",
        {
            "title": title,
            "markdown": markdown,
            "format": "docx",
            "metadata": metadata,
            "source_references": [s.to_metadata() for s in files],
            "provider": provider,
            "model": model,
        },
    )
    if not document.ok:
        gathered.notes.append(f"Saving the document failed ({document.error}). Say so.")
        return
    gathered.artifacts.append(document.data["artifact"])
    if references:
        workbook = await call_tool(
            gathered,
            tools,
            "create_spreadsheet",
            {
                "title": f"{title} — adabiyotlar",
                "sheets": [_sheet(references, works)],
                "metadata": {"action": "literature_matrix"},
            },
        )
        if workbook.ok:
            gathered.artifacts.append(workbook.data["artifact"])
    lines = [
        (
            f"EZO wrote a research plan on “{topic}”"
            if plan
            else f"EZO made a literature list on “{topic}”"
            + (" (the plan itself needs an AI model)" if want_plan else "")
        )
        + f" with {len(works)} work(s) found in OpenAlex"
        + (f" and {len(files)} of the user's file(s)" if files else "")
        + f"; the reference list ({STYLE_NAMES[style]}) was written by EZO from the works' metadata, and an Excel literature matrix was saved.",
    ]
    if search_note:
        lines.append(search_note)
    if report.bad_citations:
        lines.append(
            "Citations to works that do not exist were removed: "
            + ", ".join(report.bad_citations)
            + "."
        )
    if report.unsupported_results:
        lines.append(
            "WARNING: the draft states results the research cannot have yet (tell the user to rewrite them as hypotheses): "
            + " | ".join(report.unsupported_results[:3])
        )
    incomplete = sum(1 for r in references if r.missing())
    if incomplete:
        lines.append(
            f"{incomplete} reference(s) lack some details (marked in the workbook's last column); EZO did not fill them in."
        )
    lines.append(
        "Tell the user to read the works before citing them; EZO found them by search and did not read the full texts. Academic integrity: the plan supports the student's own work, it is not finished research. Describe the files briefly; never invent links."
    )
    gathered.notes.append("\n".join(lines))


class _Extracted(BaseModel):
    kind: str = "article"
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    title: str = ""
    container: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publisher: str = ""
    place: str = ""
    url: str = ""
    doi: str = ""


EXTRACT_SYSTEM = """Split each reference in the user's text into fields. Return ONLY JSON: {"references": [{"kind": "article"|"book"|"chapter"|"web"|"thesis"|"report", "authors": [names exactly as written], "year": int|null, "title", "container": journal/book/website, "volume", "issue", "pages", "publisher", "place", "url", "doi"}]}
Copy values exactly from the text. Leave a field empty when the text does not contain it; never add or correct anything."""


def _verified(item: _Extracted, source: str) -> tuple[Reference | None, list[str]]:
    """Keep only values that appear in the user's text."""
    text = normalize(source)
    dropped: list[str] = []

    def present(value: str) -> bool:
        return bool(value) and normalize(value) in text

    title = item.title if present(item.title) else ""
    if not title:
        return None, ["title"]
    authors = []
    for name in item.authors:
        family = re.split(r"[,\s]+", name.strip())[0]
        if family and normalize(family) in text:
            authors.append(name.strip())
        else:
            dropped.append(f"author “{name}”")
    values: dict[str, str] = {}
    for key in ("container", "volume", "issue", "pages", "publisher", "place", "url"):
        value = str(getattr(item, key) or "").strip()
        if value and not present(value):
            dropped.append(key)
            value = ""
        values[key] = value
    doi = clean_doi(item.doi)
    if doi and normalize(doi) not in text:
        dropped.append("doi")
        doi = ""
    year = item.year if item.year and str(item.year) in source else None
    if item.year and year is None:
        dropped.append("year")
    kind = (
        item.kind
        if item.kind in ("article", "book", "chapter", "web", "thesis", "report")
        else "article"
    )
    return Reference(title=title, authors=authors, year=year, kind=kind, doi=doi, **values), dropped  # type: ignore[arg-type]


async def run_citations(
    ctx: GatherContext, gathered: Gathered, style: Style, files: list[SourceRef]
) -> None:
    tools = ctx.tools
    source = inline_text(ctx.turn.text) or "\n\n".join(s.excerpt for s in files)
    if not source.strip():
        gathered.notes.append(
            "No references were given. Ask the user to paste them after a colon or attach the file."
        )
        return
    if tools.services.router.is_offline:
        gathered.notes.append(
            "Splitting references into fields needs an AI model, and none is connected. Nothing was formatted; say so."
        )
        return
    try:
        completion = await complete(
            tools.services.router,
            ROUTE,
            system=EXTRACT_SYSTEM,
            messages=[ChatMessage("user", f"<text>\n{source[:30_000]}\n</text>")],
            max_output_tokens=8_000,
        )
    except (AllProvidersFailedError, StreamInterruptedError):
        gathered.notes.append("The AI provider failed; nothing was formatted. Say so.")
        return
    gathered.tool_calls.append(completion.trace("extract_references", "references"))
    references: list[Reference] = []
    problems: list[str] = []
    for index, raw in enumerate(
        (extract_json(completion.text) or {}).get("references") or [], start=1
    ):
        try:
            item = _Extracted.model_validate(raw)
        except ValidationError:
            problems.append(f"#{index}: unreadable")
            continue
        ref, dropped = _verified(item, source)
        if ref is None:
            problems.append(f"#{index}: no title found in the text, skipped")
            continue
        references.append(ref)
        if dropped:
            problems.append(f"#{index}: removed values not in the text ({', '.join(dropped)})")
    if not references:
        gathered.notes.append(
            "No reference could be read from the text. Nothing was saved; say so."
        )
        return
    entries = format_list(references, style)
    missing = [
        f"{ref.title[:60]}: {', '.join(ref.missing())}" for ref in references if ref.missing()
    ]
    markdown = "\n".join(
        [f"# Adabiyotlar ({STYLE_NAMES[style]})", "", *[f"- {e}" for e in entries], ""]
    )
    result = await call_tool(
        gathered,
        tools,
        "create_document",
        {
            "title": f"Adabiyotlar ({STYLE_NAMES[style]})",
            "markdown": markdown,
            "format": "docx",
            "metadata": {
                "action": "citations",
                "style": style,
                "problems": problems,
                "missing": missing,
            },
            "provider": completion.provider,
            "model": completion.model,
        },
    )
    if result.ok:
        gathered.artifacts.append(result.data["artifact"])
    lines = [
        f"EZO formatted {len(references)} reference(s) in {STYLE_NAMES[style]} (rules applied by EZO, not by the model). Show them exactly:",
        *entries,
    ]
    if problems:
        lines.append("Checks: " + "; ".join(problems[:10]) + ".")
    if missing:
        lines.append(
            "Missing details the user should add (EZO did not invent them): "
            + "; ".join(missing[:10])
            + "."
        )
    gathered.notes.append("\n".join(lines))
