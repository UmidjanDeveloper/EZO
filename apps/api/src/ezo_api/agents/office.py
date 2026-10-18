"""EZO Office actions inside DocumentAgent: which files a request is about, and the
deterministic PDF operations.

Which files?
1. the files attached to this message, in the user's order;
2. otherwise, for a follow-up ("endi sahifa raqamlarini qo'y"), EZO's latest PDF in
   this conversation;
3. otherwise the newest uploads of the right type ("shu 4 ta PDF" → the 4 newest,
   oldest first).

PDF steps come from the rule-based parser (no model). Only when files are attached,
nothing was recognised and a model is available, a small planner model may propose
the same structured steps, validated by `PdfStep`; it never runs anything itself.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import or_, select

from ezo_api.agents.base import GatherContext, Gathered, call_tool
from ezo_api.agents.llm import complete, extract_json
from ezo_api.agents.references import latest_artifact
from ezo_api.core.text import normalize
from ezo_api.db.models import Artifact, KnowledgeDocument
from ezo_api.documents.pdf.requests import PdfStep, parse_pdf_request
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext

PDF_MIME = "application/pdf"
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")
_COUNT = re.compile(r"\b(\d{1,2})\s*(?:ta|x)?\s*(?:pdf|fayl|file|hujjat|файл|документ)")
_IMAGES_TO_PDF = re.compile(
    r"\bpdf\w*\s*(?:ga|qil|qilib|ga aylantir|ko'rinish)|\b(?:to|into|as) pdf\b|в pdf"
)
_FOLLOW_UP = re.compile(
    r"\b(natija|endi|yana|keyin|shu fayl|uni|now|then|this file|it\b|теперь|его|этот файл)"
)
_STEPS = TypeAdapter(list[PdfStep])

PLANNER_SYSTEM = (
    "You turn a user's request about PDF files into operations for EZO's local PDF engine.\n"
    'Reply with ONLY one JSON object: {"steps": [step, ...]} - or {"steps": []} when the '
    "request is not a PDF page/file operation (for example a question about the content, a "
    "translation, or a format conversion).\n"
    "Step fields: op (merge|delete|extract|split|rotate|move|page_numbers|watermark|"
    "header_footer|compress|clean_metadata|to_images|normalize_orientation|inspect), "
    'pages ("2", "1-3,5", "last", "4-"; 1-based, as numbered in the input), to (position '
    "for move), degrees (90|180|270), every (split size), text (watermark text or "
    "page-number template with {n}), header, footer.\n"
    "Use only what the user said; never invent page numbers or texts."
)


async def attached_files(tools: ToolContext, ids: tuple[uuid.UUID, ...]) -> list[KnowledgeDocument]:
    if not ids:
        return []
    rows = (
        await tools.session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id.in_(ids), KnowledgeDocument.user_id == tools.user_id
            )
        )
    ).all()
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


async def recent_files(
    tools: ToolContext, mimes: tuple[str, ...], count: int
) -> list[KnowledgeDocument]:
    """The newest `count` stored uploads of these types, oldest first (any ingestion status)."""
    rows = (
        await tools.session.scalars(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.user_id == tools.user_id,
                KnowledgeDocument.storage_key.is_not(None),
                KnowledgeDocument.mime_type.in_(mimes),
                or_(
                    KnowledgeDocument.project_id.is_(None),
                    KnowledgeDocument.project_id == tools.project_scope,
                ),
            )
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(count)
        )
    ).all()
    return list(reversed(rows))


def requested_count(text: str) -> int | None:
    match = _COUNT.search(normalize(text))
    return int(match.group(1)) if match else None


async def pdf_inputs(ctx: GatherContext, steps: list[PdfStep]) -> list[dict[str, str]]:
    tools, turn = ctx.tools, ctx.turn
    attached = await attached_files(tools, turn.attachments)
    usable = [d for d in attached if d.mime_type == PDF_MIME or d.mime_type in IMAGE_MIMES]
    if usable:
        return [{"kind": "document", "id": str(d.id)} for d in usable]
    merging = any(s.op == "merge" for s in steps)
    if not merging and (_FOLLOW_UP.search(normalize(turn.text)) or not turn.attachments):
        own: Artifact | None = await latest_artifact(
            tools.session, tools.user_id, tools.conversation_id, ("document",)
        )
        if own is not None:
            version = await tools.services.artifacts.current_version(tools.session, own)
            if version is not None and version.filename.lower().endswith(".pdf"):
                return [{"kind": "artifact", "id": str(own.id)}]
    count = requested_count(turn.text) or (2 if merging else 1)
    wants_images = any(s.op == "from_images" for s in steps)
    recent = await recent_files(tools, IMAGE_MIMES if wants_images else (PDF_MIME,), min(count, 20))
    return [{"kind": "document", "id": str(d.id)} for d in recent]


async def plan_with_model(ctx: GatherContext, gathered: Gathered) -> list[PdfStep]:
    tools = ctx.tools
    if tools.services.router.is_offline:
        return []
    try:
        completion = await complete(
            tools.services.router,
            "chat",
            system=PLANNER_SYSTEM,
            messages=[ChatMessage("user", ctx.turn.text[:2_000])],
            max_output_tokens=600,
            language=ctx.turn.language,
        )
    except (AllProvidersFailedError, StreamInterruptedError):
        return []
    gathered.tool_calls.append(completion.trace("plan_pdf_steps", f"{len(completion.text)} chars"))
    data: dict[str, Any] | None = extract_json(completion.text)
    try:
        return _STEPS.validate_python((data or {}).get("steps") or [])
    except ValidationError:
        return []


async def run_pdf_action(ctx: GatherContext, gathered: Gathered, *, allow_planner: bool) -> bool:
    """Handle a PDF operation request. Returns False when the request is not one."""
    turn = ctx.turn
    steps = parse_pdf_request(turn.text)
    attached = await attached_files(ctx.tools, turn.attachments)
    attached_images = [d for d in attached if d.mime_type in IMAGE_MIMES]
    if not steps and attached_images and _IMAGES_TO_PDF.search(normalize(turn.text)):
        steps = [PdfStep(op="from_images")]
    if not steps and allow_planner and any(d.mime_type == PDF_MIME for d in attached):
        steps = await plan_with_model(ctx, gathered)
    if not steps:
        return False
    inputs = await pdf_inputs(ctx, steps)
    if not inputs:
        gathered.notes.append(
            "The user asked for a PDF operation, but no PDF file was attached or found. Nothing "
            "was changed. Ask them to attach the PDF file(s) with the paperclip button."
        )
        return True
    if any(s.op == "merge" for s in steps) and len(inputs) < 2:
        gathered.notes.append(
            "Merging needs at least two PDF files, but only one was found. Nothing was changed. "
            "Ask the user to attach all the files to merge."
        )
        return True
    result = await call_tool(
        gathered,
        ctx.tools,
        "pdf_tool",
        {"inputs": inputs, "steps": [s.model_dump(exclude_none=True) for s in steps]},
    )
    if not result.ok:
        gathered.notes.append(
            f"The PDF operation could not be done: {result.error} Nothing was changed; the "
            "original files are untouched. Explain this plainly."
        )
        return True
    data = result.data or {}
    if "inspected" in data:
        info = data["inspected"]
        gathered.notes.append(
            "Facts about the PDF (computed locally, no AI): "
            f"{info['pages']} pages; text layer: {info['text_layer']}"
            + (f" (pages needing OCR: {info['scanned_pages']})" if info["scanned_pages"] else "")
            + f"; encrypted: {info['encrypted']}; digitally signed: {info['signed']}; "
            f"form fields: {info['has_forms']}; metadata: {info['metadata'] or 'none'}."
        )
        return True
    gathered.artifacts.extend(data.get("artifacts", []))
    lines = [
        "PDF operation done locally (no AI model, the original files are unchanged):",
        *[f"- {line}" for line in data.get("report", [])],
        f"- Result: {len(data.get('artifacts', []))} new file(s); page counts {data.get('pages')}; "
        "each file was reopened and its page count verified.",
    ]
    if any(s.pages for s in steps) and len(steps) > 1:
        lines.append("- Page numbers in the request were applied to the input's numbering.")
    for warning in data.get("warnings", []):
        lines.append(f"- WARNING: {warning}")
    lines.append("The files appear as cards under your message; never invent links.")
    gathered.notes.append("\n".join(lines))
    return True


# --- OCR -------------------------------------------------------------------------------------

_OCR = re.compile(
    r"\b(ocr\b|matn\w*\s+(o'qi|chiqar|ajrat|ko'chir|tanib|olib ber|yozib ber)|rasmdagi matn|"
    r"suratdagi matn|skaner\w*\s+(pdf|hujjat|fayl)\w*\s+matn|tanib ol|"
    r"распозна\w*|извлеки текст|текст с (картинк|фото|изображен|скан)\w*|"
    r"extract (the )?text|read the text|recogni[sz]e (the )?text|text from (the |this )?"
    r"(image|photo|picture|scan))"
)
_IMAGE_WORDS = re.compile(
    r"\b(ocr|rasm|surat|skaner|скан|фото|картин|изображен|image|photo|picture|scan)"
)
_OCR_LANGUAGES = [
    (re.compile(r"\b(kirill\w*|кирилл\w*|cyrillic)"), "uzb_cyrl"),
    (re.compile(r"\b(ruscha|rus tilida|русск\w*|russian)"), "rus"),
    (re.compile(r"\b(inglizcha|ingliz tilida|english|английск\w*)"), "eng"),
    (re.compile(r"\b(o'zbekcha|lotin\w*|узбек\w*|uzbek|latin)"), "uzb"),
]


def wants_ocr(text: str) -> bool:
    return bool(_OCR.search(normalize(text)))


def ocr_languages(text: str) -> list[str]:
    """Tesseract packs the user named ("kirillchada", "ruscha matn"); empty = automatic."""
    norm = normalize(text)
    return [lang for pattern, lang in _OCR_LANGUAGES if pattern.search(norm)]


async def run_ocr_action(ctx: GatherContext, gathered: Gathered) -> bool:
    """Read the text of an attached image or scanned PDF. Returns False when not asked."""
    turn = ctx.turn
    if not wants_ocr(turn.text):
        return False
    attached = await attached_files(ctx.tools, turn.attachments)
    files = [d for d in attached if d.mime_type == PDF_MIME or d.mime_type in IMAGE_MIMES]
    if not files and not turn.attachments:
        files = await recent_files(ctx.tools, (PDF_MIME, *IMAGE_MIMES), 1)
    if not files:
        if turn.attachments or not _IMAGE_WORDS.search(normalize(turn.text)):
            return False  # e.g. "matnini o'qib chiq" about a Word file: not an OCR job
        gathered.notes.append(
            "The user wants text read from an image or a scan, but no image or PDF was attached "
            "or found. Nothing was read. Ask them to attach it with the paperclip button."
        )
        return True
    languages = ocr_languages(turn.text)
    for document in files[:5]:
        result = await call_tool(
            gathered,
            ctx.tools,
            "ocr_tool",
            {"input": {"kind": "document", "id": str(document.id)}, "languages": languages},
        )
        name = document.filename or document.title
        if not result.ok:
            gathered.notes.append(
                f"OCR could not read “{name}”: {result.error} Say this plainly; do not guess "
                "what the image says."
            )
            continue
        data = result.data or {}
        if data.get("empty"):
            gathered.notes.append(
                f"OCR ran on “{name}” but recognised no text (the image may be blurry, too "
                "small or contain no text). Say so; do not guess its content."
            )
            continue
        gathered.artifacts.extend(data.get("artifacts", []))
        pages = data.get("pages", [])
        ocr_pages = [p for p in pages if p["method"] == "ocr"]
        scores = [p["confidence"] for p in ocr_pages if p.get("confidence") is not None]
        lines = [
            f"Text read from “{name}” (local OCR, {data.get('engine', {}).get('version', '')}; "
            f"{len(pages)} page(s), {len(ocr_pages)} by OCR"
            + (f", language packs {ocr_pages[0]['languages']}" if ocr_pages else "")
            + (
                f", mean Tesseract confidence {sum(scores) / len(scores):.0f}/100 — the "
                "engine's own score, not a calibrated accuracy"
                if scores
                else ""
            )
            + "). The full text is in the file card.",
            *[f"WARNING: {w}" for w in data.get("warnings", [])[:10]],
            "Show the text exactly as recognised (or its beginning if long). Do not correct, "
            "translate, complete or re-order it, and never fill in unreadable parts.",
            "RECOGNISED TEXT"
            + (" (beginning)" if data.get("truncated") else "")
            + ":\n"
            + str(data.get("preview", "")),
        ]
        gathered.notes.append("\n".join(lines))
    return True
