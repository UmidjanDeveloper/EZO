"""Professional writing in chat: "Hokimlikka xizmat xati tayyorla", "CV tayyorla",
"Bayonnoma shablonini ber".

One model call writes the content as JSON in the document type's structure; EZO checks
it (`writing.service.validate`), lays it out (`writing.render`) and stores DOCX with PDF,
Markdown and plain-text exports. A template request, or a request without an AI model,
gets the same layout with placeholders only (no model, no cost).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ezo_api.agents.base import GatherContext, Gathered, call_tool
from ezo_api.agents.llm import complete, extract_json, sources_block
from ezo_api.career.profile import cv_markdown, facts_text, load_profile
from ezo_api.core.text import normalize
from ezo_api.documents.markdown_io import parse_markdown
from ezo_api.documents.office_convert import OfficeConvertError
from ezo_api.documents.pdf.writer import render_pdf
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.organization.service import load_facts
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext
from ezo_api.tools.document_tools import artifact_entry, file_stem
from ezo_api.writing.catalog import DocType, wants_template
from ezo_api.writing.render import render_docx
from ezo_api.writing.service import (
    Draft,
    OrgFacts,
    blank,
    build_prompt,
    parse_draft,
    to_markdown,
    validate,
)
from ezo_api.writing.style import Options, options_from

_LANG = {"uz": "uz", "ru": "ru", "en": "en"}
_CAREER_DOCS = ("cv", "cover_letter", "motivatsion_xat")


async def default_organization(
    tools: ToolContext, doc: DocType | None = None
) -> tuple[OrgFacts | None, str | None]:
    """The default organization profile with its formatting, logo, template and examples."""
    facts, profile = await load_facts(
        tools.session,
        tools.services.storage,
        tools.user_id,
        doc_key=doc.key if doc else None,
        official=doc is not None and doc.layout in ("letter", "act", "minutes"),
    )
    return facts, (str(profile.id) if profile else None)


async def _pdf(tools: ToolContext, docx: bytes, markdown: str, title: str) -> tuple[bytes, str]:
    """PDF of the Word file: LibreOffice layout when installed, else EZO's text PDF."""
    if tools.services.office is not None:
        try:
            result = await tools.services.office.to_pdf(docx, "docx")
            return result.pdf, result.engine
        except OfficeConvertError:
            pass
    pdf = await asyncio.to_thread(lambda: render_pdf(parse_markdown(markdown, title=title)))
    return pdf, "EZO text layout"


async def write_document(
    ctx: GatherContext, gathered: Gathered, doc: DocType, sources: list[SourceRef]
) -> None:
    tools = ctx.tools
    text = ctx.turn.text
    options: Options = options_from(text)
    language = options.language or _LANG.get(ctx.turn.language, "uz")
    org, org_id = await default_organization(tools, doc)
    career = await load_profile(tools.session, tools.user_id) if doc.key in _CAREER_DOCS else None
    if doc.key == "cv" and career is not None and not wants_template(normalize(text)):
        await _cv_from_profile(ctx, gathered, career, language)
        return
    template = wants_template(normalize(text)) or tools.services.router.is_offline
    draft: Draft | None
    provider = model = None
    if template:
        draft = blank(doc, language)
    else:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        words = options.words or doc.words
        context = [f"User's request:\n{text}"]
        if org is not None and career is None:
            context.append(f"Organization profile (entered by the user):\n{org.block()}")
        if org is not None and org.examples:
            context.append(org.examples_block())
        if career is not None:
            context.append(
                "Career profile (entered by the user; the ONLY facts about their experience, "
                f"education, skills and achievements):\n{facts_text(career)}"
            )
        if sources:
            context.append(sources_block(sources))
        try:
            completion = await complete(
                tools.services.router,
                "reasoning" if words[1] > 900 else "chat",
                system=build_prompt(doc, options, language),
                messages=[ChatMessage("user", "\n\n".join(context))],
                max_output_tokens=min(16_000, int(words[1] * 3) + 1_500),
                language=ctx.turn.language,
            )
        except (AllProvidersFailedError, StreamInterruptedError):
            gathered.notes.append(
                "The AI provider failed, so the document was not written. Offer the template "
                "(say “shablon”) or to try again. Nothing was saved."
            )
            return
        gathered.tool_calls.append(
            completion.trace(f"write_{doc.key}", f"{len(completion.text)} chars")
        )
        provider, model = completion.provider, completion.model
        draft = parse_draft(extract_json(completion.text))
        if draft is None:
            gathered.notes.append(
                "The model's draft could not be read (not in the expected structure). Nothing "
                "was saved; say so and offer to try again or to make the template."
            )
            return
    evidence = " ".join(
        [
            text,
            org.text() if org else "",
            facts_text(career) if career else "",
            *(s.excerpt for s in sources),
        ]
    )
    report = validate(doc, draft, evidence=evidence, options=options, language=language)
    if not draft.title:
        draft.title = doc.names.get(
            "uz" if language.startswith("uz") else language, doc.names["uz"]
        )
    docx = await asyncio.to_thread(
        render_docx, doc, draft, org=org, language=language, draft_label=options.draft_label
    )
    markdown = to_markdown(doc, draft, org)
    pdf, pdf_engine = await _pdf(tools, docx, markdown, draft.title)
    stem = file_stem(draft.title, doc.key)
    metadata: dict[str, Any] = {
        "action": "template" if template else "write",
        "doc_type": doc.key,
        "mode": options.mode or doc.mode,
        "language": language,
        "draft": doc.draft and options.draft_label,
        "organization_profile_id": org_id,
        "validation": report.summary(),
        "missing": draft.missing[:20],
        "pdf_engine": pdf_engine,
        "organization_template": org.template_title if org and org.template else None,
        "organization_examples": [t for t, _ in org.examples] if org else [],
        "options": {"words": options.words, "audience": options.audience},
    }
    created = await tools.services.artifacts.create(
        tools.session,
        tools.user_id,
        title=draft.title,
        artifact_type="report" if doc.key == "hisobot" else "document",
        filename=f"{stem}.docx",
        data=docx,
        project_id=tools.project_scope,
        conversation_id=tools.conversation_id,
        created_by_agent="document",
        provider=provider,
        model=model,
        generation_metadata=metadata,
        source_references=[s.to_metadata() for s in sources],
        exports={
            "pdf": (f"{stem}.pdf", pdf),
            "markdown": (f"{stem}.md", markdown.encode("utf-8")),
            "text": (f"{stem}.txt", re.sub(r"[#*]", "", markdown).encode("utf-8")),
        },
        change_summary="Template" if template else "Draft",
    )
    gathered.artifacts.append(artifact_entry(created))
    gathered.sources = sources
    gathered.notes.append(_note(doc, draft, report.summary(), template, metadata["draft"], tools))
    if doc.key in _CAREER_DOCS and career is None:
        gathered.notes.append(
            "Suggest filling the career profile (Settings → Karyera profili): EZO then builds "
            "the CV exactly from it and uses it as the only facts for application letters."
        )
    elif career is not None:
        gathered.notes.append("The letter uses the user's career profile as its only facts.")


def _note(
    doc: DocType,
    draft: Draft,
    report: dict[str, Any],
    template: bool,
    is_draft: bool,
    tools: ToolContext,
) -> str:
    name = doc.names["uz"]
    lines = [
        (
            f"EZO made a {name} TEMPLATE (structure and placeholders only, no AI text"
            + (" — no AI model is available right now" if tools.services.router.is_offline else "")
            + ")."
            if template
            else f"EZO drafted the {name} in the official layout (Word + PDF, also .md/.txt)."
        ),
    ]
    if is_draft:
        lines.append(
            "It is a DRAFT (the page header says QORALAMA): it becomes an official document only "
            "after an authorized person reviews, signs and registers it. Signature and seal "
            "places are placeholders."
        )
    if report["placeholders"]:
        lines.append("Placeholders to fill in: " + ", ".join(report["placeholders"][:15]) + ".")
    if report["replaced_fields"]:
        lines.append(
            "These details were left as placeholders because the user did not give them: "
            + ", ".join(report["replaced_fields"])
            + "."
        )
    if report["unverified_numbers"]:
        lines.append(
            "Numbers/dates in the text that the user did not give (ask them to check): "
            + ", ".join(report["unverified_numbers"][:10])
            + "."
        )
    if report["approval_claims"]:
        lines.append(
            "WARNING: the text claims signing/approval ("
            + ", ".join(report["approval_claims"])
            + "); tell the user to remove it."
        )
    if report["style"]:
        lines.append("Style notes found by EZO: " + "; ".join(report["style"][:5]) + ".")
    if report["length_note"]:
        lines.append(f"Length: {report['length_note']}.")
    if report["script_note"]:
        lines.append(f"Script: {report['script_note']}.")
    if draft.missing:
        lines.append("Ask the user for: " + "; ".join(draft.missing[:8]) + ".")
    lines.append("Describe the file briefly; do not paste the whole document. Never invent links.")
    return "\n".join(lines)


async def _cv_from_profile(
    ctx: GatherContext, gathered: Gathered, career: Any, language: str
) -> None:
    """A CV exactly from the career profile: no model, nothing added."""
    result = await call_tool(
        gathered,
        ctx.tools,
        "create_document",
        {
            "title": f"CV — {career.full_name}",
            "markdown": cv_markdown(career, language),
            "format": "docx",
            "metadata": {"action": "cv", "source": "career_profile", "language": language},
        },
    )
    if not result.ok:
        gathered.notes.append(f"Saving the CV failed ({result.error}). Say so.")
        return
    gathered.artifacts.append(result.data["artifact"])
    gathered.notes.append(
        "EZO built the CV (Word + PDF) EXACTLY from the user's career profile, without an AI "
        "model: nothing was added or reworded. Section headings follow the requested language; "
        "the entries stay as the user wrote them (EZO does not translate them). To change it, "
        "edit the profile in Settings → Karyera profili. Describe it briefly; do not paste it."
    )
