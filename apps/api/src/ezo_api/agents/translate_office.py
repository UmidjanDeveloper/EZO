# ruff: noqa: E501  (note texts are kept on readable lines)
"""Translation in chat (Stage C): text in the message, Uzbek script conversion of text and
files, and the glossary ("Glossariyga qo'sh: «hokimlik» → «khokimiyat»").

Files in another language are translated by `DocumentAgent._transform`, which calls
`translation_plan`, `load_glossary` and `docx_review` from here: Word files are edited
in place (DOCX fidelity), other files through Markdown, long ones part by part.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from ezo_api.agents.base import GatherContext, Gathered
from ezo_api.agents.docx_office import docx_from_document, find_docx
from ezo_api.agents.office import attached_files
from ezo_api.agents.writing_office import default_organization
from ezo_api.core.text import normalize
from ezo_api.db.models import DocumentRevision, GlossaryTerm, KnowledgeDocument
from ezo_api.documents.docx.fidelity import DocxEditError, docx_text
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.security.audit import audit
from ezo_api.tools.base import ToolContext
from ezo_api.tools.document_tools import artifact_entry, file_stem
from ezo_api.translation import glossary
from ezo_api.translation.documents import bilingual_docx, docx_pairs, transliterate_docx
from ezo_api.translation.languages import (
    LABELS,
    NAMES,
    base,
    default_target,
    detect,
    domain_of,
    parse_languages,
)
from ezo_api.translation.quality import QualityReport, check
from ezo_api.translation.requests import (
    BILINGUAL,
    SCRIPT_VERB,
    SCRIPT_WORD,
    TRANSLATE,
    inline_text,
)
from ezo_api.translation.service import TranslationError, pairs_of, translate_text
from ezo_api.translation.translit import Script, detect_script, transliterate

NOTE_CHARS = 6_000


@dataclass(slots=True)
class TranslationPlan:
    source: str
    target: str
    domain: str
    bilingual: bool


def translation_plan(request: str, source_text: str, user_language: str) -> TranslationPlan:
    named = parse_languages(request)
    source = named.source or detect(source_text)
    if named.source and base(named.source) == "uz":
        source = detect(source_text) if base(detect(source_text)) == "uz" else named.source
    target = named.target or default_target(source, user_language)
    return TranslationPlan(
        source=source,
        target=target,
        domain=domain_of(request),
        bilingual=bool(BILINGUAL.search(normalize(request))),
    )


async def load_glossary(tools: ToolContext, source: str, target: str) -> list[glossary.Term]:
    _, org_id = await default_organization(tools)
    return await glossary.load_terms(
        tools.session,
        tools.user_id,
        source,
        target,
        uuid.UUID(org_id) if org_id else None,
    )


def quality_note(report: QualityReport) -> str:
    lines = report.lines()
    if not lines:
        return "EZO's checks found no problem (numbers, dates, links, names, glossary terms, paragraphs)."
    return "EZO's checks (tell the user; these need a human look):\n" + "\n".join(
        f"- {line}" for line in lines
    )


# --------------------------------------------------------------------------- glossary


async def run_glossary_action(ctx: GatherContext, gathered: Gathered) -> bool:
    pair = glossary.add_request(ctx.turn.text)
    if pair is None:
        return False
    tools = ctx.tools
    source_term, target_term = pair
    named = parse_languages(ctx.turn.text)
    source = base(named.source or detect(source_term))
    target = base(named.target or detect(target_term))
    if source == target:
        gathered.notes.append(
            f"The user wants to save the glossary pair “{source_term}” → “{target_term}”, but "
            "EZO cannot tell the two languages apart. Nothing was saved. Ask them to name the "
            "target language, e.g. “Glossariyga qo'sh (inglizcha): «…» → «…»”."
        )
        return True
    if len(source_term) > 300 or len(target_term) > 300:
        gathered.notes.append("A glossary term is longer than 300 characters. Nothing was saved.")
        return True
    existing = await tools.session.scalar(
        select(GlossaryTerm).where(
            GlossaryTerm.user_id == tools.user_id,
            GlossaryTerm.organization_id.is_(None),
            GlossaryTerm.source_language == source,
            GlossaryTerm.target_language == target,
            func.lower(GlossaryTerm.source_term) == source_term.lower(),
        )
    )
    if existing is not None:
        existing.target_term = target_term
        term = existing
    else:
        term = GlossaryTerm(
            user_id=tools.user_id,
            source_language=source,
            target_language=target,
            source_term=source_term,
            target_term=target_term,
        )
        tools.session.add(term)
    await tools.session.flush()
    audit(
        tools.session,
        tools.user_id,
        "glossary.update" if existing else "glossary.create",
        "glossary_term",
        term.id,
        {"source_language": source, "target_language": target},
    )
    gathered.tool_calls.append(
        {"tool": "glossary_save", "ok": True, "summary": f"{source}→{target}", "error": None}
    )
    gathered.notes.append(
        f"Saved in the user's glossary ({NAMES[source]} → {NAMES[target]}): “{source_term}” → "
        f"“{target_term}”{' (updated)' if existing else ''}. EZO will use it in translations "
        "between these languages and check that it was used. It can be edited on the "
        "Translation page."
    )
    return True


# --------------------------------------------------------------------------- script conversion


@dataclass(slots=True)
class _Input:
    title: str
    text: str
    docx: Any = None
    document: KnowledgeDocument | None = None
    references: list[dict[str, Any]] = field(default_factory=list)


async def _document_text(tools: ToolContext, document: KnowledgeDocument) -> str:
    if document.current_revision_id is None:
        return ""
    revision = await tools.session.get(DocumentRevision, document.current_revision_id)
    return (revision.raw_text or "") if revision is not None else ""


async def _input(ctx: GatherContext) -> _Input | None:
    """What a script conversion works on: text in the message, an attached file, or EZO's
    latest Word document in this conversation."""
    text = inline_text(ctx.turn.text)
    if text is not None and not ctx.turn.attachments:
        return _Input("Matn", text)
    tools = ctx.tools
    for document in await attached_files(tools, ctx.turn.attachments):
        docx = await docx_from_document(tools, document)
        reference = {"kind": "file", "document_id": str(document.id), "title": document.title}
        if docx is not None:
            body = await asyncio.to_thread(docx_text, docx.data)
            return _Input(
                document.title, body, docx=docx, document=document, references=[reference]
            )
        body = await _document_text(tools, document)
        if body.strip():
            return _Input(document.title, body, document=document, references=[reference])
    if ctx.turn.attachments:
        return None
    docx = await find_docx(ctx, None)
    if docx is None:
        return None
    body = await asyncio.to_thread(docx_text, docx.data)
    return _Input(docx.title, body, docx=docx, references=[docx.reference()])


async def run_translit_action(ctx: GatherContext, gathered: Gathered) -> bool:
    """Uzbek Latin ↔ Cyrillic without a model: "Kirillga o'gir", "Lotin yozuviga o'tkaz",
    or "o'zbek kirilliga tarjima qil" for a text that is already Uzbek."""
    text = ctx.turn.text
    norm = normalize(text)
    script_request = bool(SCRIPT_WORD.search(norm) and SCRIPT_VERB.search(norm))
    if not (script_request or TRANSLATE.search(norm)):
        return False
    named = parse_languages(text)
    if named.target not in ("uz", "uz-cyrl") and not script_request:
        return False
    source = await _input(ctx)
    if source is None or not source.text.strip():
        return False
    current = detect_script(source.text)
    uzbek = base(detect(source.text)) == "uz"
    # "Tarjima qil" changes only the script of a text that is already Uzbek; a plain
    # "kirillga/lotinga o'gir" also accepts Cyrillic text without ў, қ, ғ, ҳ (it looks Russian).
    if not (uzbek or (current == "cyrillic" and not TRANSLATE.search(norm))):
        return False  # another language: a translation, not a script change
    to: Script
    if named.target == "uz-cyrl":
        to = "cyrillic"
    elif named.target == "uz":
        to = "latin"
    else:
        to = "latin" if current == "cyrillic" else "cyrillic"
    target = "uz-cyrl" if to == "cyrillic" else "uz"
    if current == to:
        gathered.notes.append(
            f"“{source.title}” is already in {'Cyrillic' if to == 'cyrillic' else 'Latin'} "
            "script. Nothing was changed; say so."
        )
        return True
    tools = ctx.tools
    label = "Кирилл" if to == "cyrillic" else "Lotin"
    if source.docx is not None:
        try:
            data, changed = await asyncio.to_thread(transliterate_docx, source.docx.data, to)
        except DocxEditError as exc:
            gathered.notes.append(f"The Word file could not be converted: {exc.message} Say so.")
            return True
        converted = transliterate(source.text, to)
        stem = file_stem(source.docx.filename.rsplit(".", 1)[0], "document")
        filename = f"{stem} ({label}).docx"
        report = check(
            docx_pairs(source.docx.data, data), source_language="uz", target_language=target
        )
        meta: dict[str, Any] = {
            "action": "transliterate",
            "fidelity": "in_place",
            "script": to,
            "paragraphs_changed": changed,
            "engine": "EZO transliteration rules (no AI model)",
            "inputs": [source.docx.provenance()],
            "translation_quality": report.summary(),
        }
        exports = {"markdown": (f"{stem} ({label}).md", converted.encode("utf-8"))}
        artifacts = tools.services.artifacts
        if source.docx.artifact is not None:
            created = await artifacts.add_version(
                tools.session,
                source.docx.artifact,
                filename=source.docx.filename,
                data=data,
                created_by="document",
                generation_metadata=meta,
                source_references=source.references,
                change_summary=f"Script: {label}",
                exports=exports,
            )
        else:
            created = await artifacts.create(
                tools.session,
                tools.user_id,
                title=f"{source.title} ({label})",
                artifact_type="document",
                filename=filename,
                data=data,
                project_id=tools.project_scope,
                conversation_id=tools.conversation_id,
                created_by_agent="document",
                generation_metadata=meta,
                source_references=source.references,
                exports=exports,
                change_summary=f"Script: {label}",
            )
        gathered.artifacts.append(artifact_entry(created))
        gathered.notes.append(
            f"EZO converted “{source.title}” to {'Cyrillic' if to == 'cyrillic' else 'Latin'} "
            f"script IN THE ORIGINAL WORD FILE ({changed} paragraphs; formatting, tables, "
            "headers and footers kept), locally by fixed rules without an AI model. Loanwords "
            "with ц and the soft sign follow a small built-in list; ask the user to proofread "
            "names and foreign words. Describe it briefly; do not paste the document."
        )
        return True
    converted = transliterate(source.text, to)
    stem = file_stem(source.title, "matn")
    created = await tools.services.artifacts.create(
        tools.session,
        tools.user_id,
        title=f"{source.title} ({label})",
        artifact_type="document",
        filename=f"{stem} ({label}).txt",
        data=converted.encode("utf-8"),
        project_id=tools.project_scope,
        conversation_id=tools.conversation_id,
        created_by_agent="document",
        generation_metadata={
            "action": "transliterate",
            "script": to,
            "engine": "EZO transliteration rules (no AI model)",
            "layout_kept": False,
        },
        source_references=source.references,
        change_summary=f"Script: {label}",
    )
    gathered.artifacts.append(artifact_entry(created))
    shown = converted[:NOTE_CHARS]
    gathered.notes.append(
        f"EZO converted the text to {'Cyrillic' if to == 'cyrillic' else 'Latin'} script "
        "locally by fixed rules (no AI model) and saved it as a .txt file"
        + (" (the file's layout is not kept: only its text)" if source.document else "")
        + ". Show the result exactly as below, without changing a letter"
        + (" (it is shortened here; the file has all of it)" if len(converted) > NOTE_CHARS else "")
        + f":\n<converted>\n{shown}\n</converted>"
    )
    return True


# --------------------------------------------------------------------------- text in chat


async def run_inline_translation(ctx: GatherContext, gathered: Gathered) -> bool:
    """ "Inglizchaga tarjima qil: …" — the text is in the message (no file)."""
    if ctx.turn.attachments or not TRANSLATE.search(normalize(ctx.turn.text)):
        return False
    text = inline_text(ctx.turn.text)
    if text is None:
        return False
    tools = ctx.tools
    plan = translation_plan(ctx.turn.text, text, ctx.turn.language)
    if tools.services.router.is_offline:
        gathered.notes.append(
            "No AI provider is connected, so EZO cannot translate now (Uzbek Latin ↔ Cyrillic "
            "conversion still works without one). Nothing was translated; say so plainly."
        )
        return True
    terms = await load_glossary(tools, plan.source, plan.target)
    if tools.on_activity is not None:
        tools.on_activity("creating")
    try:
        result = await translate_text(
            tools.services.router,
            text,
            source=plan.source,
            target=plan.target,
            domain=plan.domain,
            terms=terms,
            request=ctx.turn.text[: len(ctx.turn.text) - len(text)][:300],
            on_call=lambda c: gathered.tool_calls.append(c.trace("translate_text", plan.target)),
        )
    except TranslationError as exc:
        gathered.notes.append(f"The translation was not done: {exc.message} Say so.")
        return True
    except (AllProvidersFailedError, StreamInterruptedError):
        gathered.notes.append("The AI provider failed; nothing was translated. Say so.")
        return True
    if plan.bilingual or len(result.text) > NOTE_CHARS:
        data = await asyncio.to_thread(
            bilingual_docx,
            pairs_of(text, result.text),
            title=f"Tarjima: {LABELS.get(plan.source, plan.source)} → {LABELS.get(plan.target, plan.target)}",
            source_label=LABELS.get(plan.source, plan.source),
            target_label=LABELS.get(plan.target, plan.target),
        )
        created = await tools.services.artifacts.create(
            tools.session,
            tools.user_id,
            title=f"Tarjima ({plan.target})",
            artifact_type="document",
            filename=f"tarjima-{plan.target}.docx",
            data=data,
            project_id=tools.project_scope,
            conversation_id=tools.conversation_id,
            created_by_agent="document",
            provider=result.provider,
            model=result.model,
            generation_metadata={"action": "translate", "bilingual": True, **result.summary()},
            exports={"text": (f"tarjima-{plan.target}.txt", result.text.encode("utf-8"))},
            change_summary=f"Translated to {NAMES.get(plan.target, plan.target)}",
        )
        gathered.artifacts.append(artifact_entry(created))
    shown = result.text[:NOTE_CHARS]
    gathered.notes.append(
        f"EZO translated the user's text from {NAMES.get(plan.source)} into "
        f"{NAMES.get(plan.target)} ({plan.domain} style"
        + (f"; {len(result.terms)} glossary term(s) applied" if result.terms else "")
        + "). Give the translation exactly as below"
        + (
            " (shortened here; the bilingual Word file has all of it)"
            if len(result.text) > NOTE_CHARS
            else ""
        )
        + ", then the check results briefly.\n"
        f"<translation>\n{shown}\n</translation>\n" + quality_note(result.quality)
    )
    return True


# --------------------------------------------------------------------------- Word files


@dataclass(slots=True)
class Review:
    data: bytes
    meta: dict[str, Any]
    warnings: list[str]
    exports: dict[str, tuple[str, bytes]]
    lines: list[str]


def docx_review(
    plan: TranslationPlan, terms: list[glossary.Term], title: str
) -> Callable[[bytes, bytes], Awaitable[Review]]:
    """Runs after a Word file was translated in place: Cyrillic conversion when asked,
    the quality checks, and a bilingual export when asked."""

    async def review(before: bytes, after: bytes) -> Review:
        data = after
        if plan.target == "uz-cyrl":
            data, _ = await asyncio.to_thread(transliterate_docx, after, "cyrillic")
        pairs = await asyncio.to_thread(docx_pairs, before, data)
        report = check(pairs, source_language=plan.source, target_language=plan.target, terms=terms)
        exports: dict[str, tuple[str, bytes]] = {}
        if plan.bilingual:
            bilingual = await asyncio.to_thread(
                bilingual_docx,
                pairs,
                title=title,
                source_label=LABELS.get(plan.source, plan.source),
                target_label=LABELS.get(plan.target, plan.target),
            )
            exports["bilingual"] = (f"{file_stem(title, 'tarjima')} (bilingual).docx", bilingual)
        return Review(
            data=data,
            meta={
                "translation": {
                    "source_language": plan.source,
                    "target_language": plan.target,
                    "domain": plan.domain,
                    "terms": [{"source": t.source, "target": t.target} for t in terms],
                    "bilingual": plan.bilingual,
                },
                "translation_quality": report.summary(),
            },
            warnings=report.lines(),
            exports=exports,
            lines=[
                f"Translated from {NAMES.get(plan.source)} into {NAMES.get(plan.target)}"
                + (f" with {len(terms)} glossary term(s)" if terms else "")
                + (
                    "; a two-column bilingual Word file is attached as an extra download"
                    if plan.bilingual
                    else ""
                )
                + ".",
                quality_note(report),
            ],
        )

    return review


# --------------------------------------------------------------------------- other files


async def finish_markdown_translation(
    ctx: GatherContext,
    gathered: Gathered,
    plan: TranslationPlan,
    terms: list[glossary.Term],
    source_text: str,
    markdown: str,
    title: str,
) -> tuple[str, dict[str, Any], list[str]]:
    """After a non-Word file was translated through Markdown: Cyrillic conversion when
    asked, the quality checks and, when asked, a bilingual Word file."""
    if plan.target == "uz-cyrl":
        markdown = transliterate(markdown, "cyrillic")
    body = (
        re.sub(r"\A#[^\n]*\n+", "", markdown)
        if not source_text.lstrip().startswith("#")
        else markdown
    )
    pairs = pairs_of(source_text, body)
    report = check(pairs, source_language=plan.source, target_language=plan.target, terms=terms)
    lines = [
        f"Translated from {NAMES.get(plan.source)} into {NAMES.get(plan.target)}"
        + (f" with {len(terms)} glossary term(s)" if terms else "")
        + ".",
        quality_note(report),
    ]
    if plan.bilingual:
        tools = ctx.tools
        aligned = len(pairs) > 1 or len(source_text) < 4_000
        data = await asyncio.to_thread(
            bilingual_docx,
            pairs if aligned else [(source_text, body)],
            title=title,
            source_label=LABELS.get(plan.source, plan.source),
            target_label=LABELS.get(plan.target, plan.target),
        )
        created = await tools.services.artifacts.create(
            tools.session,
            tools.user_id,
            title=f"{title} (bilingual)",
            artifact_type="document",
            filename=f"{file_stem(title, 'tarjima')} (bilingual).docx",
            data=data,
            project_id=tools.project_scope,
            conversation_id=tools.conversation_id,
            created_by_agent="document",
            generation_metadata={"action": "translate", "bilingual": True, "rows": len(pairs)},
            change_summary="Bilingual translation",
        )
        gathered.artifacts.append(artifact_entry(created))
        lines.append(
            "A two-column bilingual Word file was also saved"
            + (
                ""
                if len(pairs) > 1
                else " (the paragraphs could not be paired one to one, so the texts sit side by side as wholes)"
            )
            + "."
        )
    meta = {
        "translation": {
            "source_language": plan.source,
            "target_language": plan.target,
            "domain": plan.domain,
            "terms": [{"source": t.source, "target": t.target} for t in terms],
            "bilingual": plan.bilingual,
        },
        "translation_quality": report.summary(),
    }
    return markdown, meta, lines
