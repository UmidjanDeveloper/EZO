"""Education materials in chat (Stage D): "7-sinf uchun fotosintez mavzusida 45 daqiqalik
dars ishlanmasi tayyorla", "Shu ma'ruzadan 10 ta test tuz", "Sillabus tuz", "Baholash
mezonlarini tuz", "IELTSga 6 haftalik tayyorgarlik rejasini tuz".

One model call writes the content as JSON; EZO checks it (`education.models.check`) and
produces a Word document (+ PDF), an Excel workbook (questions with the answer key,
timing, rubric, schedule) and, for lessons or when slides are asked for, a presentation
through the existing presentation engine. Without a model (or for "shablon") the same
files are made from a template with placeholders.
"""

from __future__ import annotations

from typing import Any

from ezo_api.agents.base import GatherContext, Gathered, call_tool
from ezo_api.agents.llm import complete, extract_json, sources_block
from ezo_api.career.profile import facts_text, load_profile
from ezo_api.core.text import normalize
from ezo_api.education.catalog import Kind, options_from
from ezo_api.education.models import build_prompt, check, parse
from ezo_api.education.render import blank, to_deck, to_markdown, to_sheets
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.translation.translit import to_cyrillic
from ezo_api.writing.catalog import wants_template
from ezo_api.writing.service import LANGUAGE_NAMES
from ezo_api.writing.style import options_from as style_options

ROUTE = "chat"


def _cyrillic(value: Any) -> Any:
    """Uzbek Latin → Cyrillic in every string of a nested structure."""
    if isinstance(value, str):
        return to_cyrillic(value)
    if isinstance(value, list):
        return [_cyrillic(v) for v in value]
    if isinstance(value, dict):
        return {
            k: (_cyrillic(v) if k not in ("layout", "language") else v) for k, v in value.items()
        }
    return value


async def make_material(
    ctx: GatherContext, gathered: Gathered, kind: Kind, sources: list[SourceRef]
) -> None:
    tools = ctx.tools
    text = ctx.turn.text
    options = options_from(text)
    language = style_options(text).language or {"ru": "ru", "en": "en"}.get(ctx.turn.language, "uz")
    model_language = "uz" if language == "uz-cyrl" else language
    template = wants_template(normalize(text)) or tools.services.router.is_offline
    provider = model = None
    if template:
        material = blank(kind, options, model_language)
    else:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        context = [f"User's request:\n{text}"]
        if kind.key == "interview":
            career = await load_profile(tools.session, tools.user_id)
            context.append(
                "Career profile (entered by the user; the only facts about them):\n"
                + (facts_text(career) if career else "(none — the user has not filled it in)")
            )
        if sources:
            context.append(sources_block(sources))
        questions = options.questions or 10
        try:
            completion = await complete(
                tools.services.router,
                ROUTE,
                system=build_prompt(
                    kind,
                    options,
                    LANGUAGE_NAMES.get(model_language, model_language),
                    options.level or "",
                ),
                messages=[ChatMessage("user", "\n\n".join(context))],
                max_output_tokens=12_000
                if kind.key in ("lesson", "syllabus")
                else min(12_000, 1_500 + questions * 300),
                language=ctx.turn.language,
            )
        except (AllProvidersFailedError, StreamInterruptedError):
            gathered.notes.append(
                "The AI provider failed, so nothing was made. Offer the template (say "
                "“shablon”) or to try again."
            )
            return
        gathered.tool_calls.append(
            completion.trace(f"education_{kind.key}", f"{len(completion.text)} chars")
        )
        provider, model = completion.provider, completion.model
        parsed = parse(extract_json(completion.text))
        if parsed is None:
            gathered.notes.append(
                "The model's answer could not be read (not in the expected structure). Nothing "
                "was saved; say so and offer to try again or to make the template."
            )
            return
        material = parsed
    report = check(kind, material, options)
    markdown = to_markdown(kind, material, report, model_language)
    sheets = to_sheets(kind, material, report, model_language) if "xlsx" in kind.outputs else []
    deck = (
        to_deck(material, model_language)
        if not template and ("pptx" in kind.outputs or options.slides)
        else None
    )
    if language == "uz-cyrl":
        markdown, sheets, deck = to_cyrillic(markdown), _cyrillic(sheets), _cyrillic(deck)
    title = (material.title or kind.names.get(model_language, kind.names["en"]))[:200]
    if language == "uz-cyrl":
        title = to_cyrillic(title)
    metadata: dict[str, Any] = {
        "action": "education",
        "kind": kind.key,
        "template": template,
        "language": language,
        "check": report.summary(),
        "options": {
            "questions": options.questions,
            "minutes": options.minutes,
            "weeks": options.weeks,
            "level": options.level,
        },
        "sources_needed": material.sources_needed[:20],
    }
    references = [s.to_metadata() for s in sources]
    made: list[str] = []
    document = await call_tool(
        gathered,
        tools,
        "create_document",
        {
            "title": title,
            "markdown": markdown,
            "format": "docx",
            "metadata": metadata,
            "source_references": references,
            "provider": provider,
            "model": model,
        },
    )
    if not document.ok:
        gathered.notes.append(f"Saving the document failed ({document.error}). Say so.")
        return
    gathered.artifacts.append(document.data["artifact"])
    made.append("a Word document (+ PDF)")
    if sheets:
        workbook = await call_tool(
            gathered,
            tools,
            "create_spreadsheet",
            {
                "title": title,
                "sheets": sheets,
                "metadata": {"action": "education", "kind": kind.key},
                "provider": provider,
                "model": model,
            },
        )
        if workbook.ok:
            gathered.artifacts.append(workbook.data["artifact"])
            made.append("an Excel workbook (" + ", ".join(s["name"] for s in sheets) + ")")
    if deck is not None:
        slides = await call_tool(
            gathered,
            tools,
            "create_presentation",
            {"deck": deck, "source_references": references, "provider": provider, "model": model},
        )
        if slides.ok:
            gathered.artifacts.append(slides.data["artifact"])
            made.append(f"a presentation ({len(deck['slides'])} slides)")
        else:
            gathered.notes.append(f"The slides could not be made: {slides.error}")
    gathered.sources = sources
    gathered.notes.append(
        _note(
            kind,
            made,
            report.summary(),
            template,
            material.sources_needed,
            tools.services.router.is_offline,
        )
    )


def _note(
    kind: Kind,
    made: list[str],
    report: dict[str, Any],
    template: bool,
    sources_needed: list[str],
    offline: bool,
) -> str:
    lines = [
        (
            f"EZO made a {kind.names['en'].lower()} TEMPLATE with placeholders (no AI text"
            + (" — no AI model is connected" if offline else "")
            + "): "
            if template
            else f"EZO prepared the {kind.names['en'].lower()}: "
        )
        + "; ".join(made)
        + "."
    ]
    if report["answer_key"] and not template:
        lines.append(
            "The answer key was built by EZO from the questions and is in the document's last "
            "section and in the workbook."
        )
    if report["issues"]:
        lines.append(
            "EZO's checks found (tell the user): " + "; ".join(report["issues"][:10]) + "."
        )
    if report["max_points"]:
        lines.append(f"Rubric maximum: {report['max_points']} points.")
    if sources_needed:
        lines.append(
            "Sources are not invented; the files list the kinds of sources still needed: "
            + "; ".join(sources_needed[:5])
            + "."
        )
    lines.append(
        "Remind the user to review the content before using it with learners. Describe the "
        "files briefly; do not paste them. Never invent links."
    )
    return "\n".join(lines)
