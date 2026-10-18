# ruff: noqa: E501  (prompt text is kept on readable lines)
"""Word documents edited in place (EZO Office, Phase 3 step 3).

Translation, proofreading and style changes of a .docx keep the original file's
formatting: the model only sees and returns paragraph texts (numbered, with ⟦k⟧ markers
for inline formatting), and `documents.docx.fidelity` writes them back into the original
XML. The whole document is processed in batches, so nothing is silently cut off.

"«X» ni «Y» ga almashtir" is a deterministic find-and-replace that needs no model.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ezo_api.agents.base import GatherContext, Gathered
from ezo_api.agents.llm import complete
from ezo_api.agents.office import attached_files
from ezo_api.agents.references import latest_artifact
from ezo_api.core.text import normalize, quoted
from ezo_api.db.models import Artifact, KnowledgeDocument
from ezo_api.documents.docx import fidelity
from ezo_api.documents.docx.fidelity import DOCX_MIME, DocxEditError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext
from ezo_api.tools.document_tools import artifact_entry, file_stem

BATCH_CHARS = 6_000
BATCH_PARAGRAPHS = 60
MAX_EDIT_CHARS = 400_000
"""Longest document edited in one request (about 150 pages); longer ones are refused with
an explanation instead of being cut."""

DOCX_EDIT_SYSTEM = """You are EZO's Word document editor. Task: {task}
The input is the document's paragraphs, one per line: "[[n]] text".
Reply with ONLY lines of the form "[[n]] new text" — {coverage}.
Rules:
- Keep each paragraph's number. One line per paragraph: never merge, split, reorder or add paragraphs.
- Text between ⟦k⟧ and ⟦/k⟧ has special formatting (bold, colour, a link). Keep the same markers around the words that correspond to it.
- Keep ⟨TAB⟩ and ⟨BR⟩ tokens where they belong.
- Keep numbers, amounts, dates, names and document numbers exactly, unless the task itself requires a change.
- Never add facts. No comments, no explanations, no code fences."""

_LINE = re.compile(r"^\s*\[\[(\d{1,6})\]\]\s?(.*)$")
_TRACKED = re.compile(
    r"\b(track changes|tracked changes|o'zgarishlar\w* (ko'rsat|belgila|ko'rinsin)|"
    r"tahrir rejim\w*|режим(е)? (правок|рецензирования)|правк\w* видн|с исправлениями|"
    r"show (the )?changes|record(ed)? changes)"
)
_REPLACE_VERB = re.compile(
    r"\b(almashtir|o'zgartir|alishtir|replace|change|substitute|замени|поменяй|измени)"
)


def wants_tracked_changes(text: str) -> bool:
    return bool(_TRACKED.search(normalize(text)))


def replacement_request(text: str) -> tuple[str, str] | None:
    """(old, new) from «X» ni «Y» ga almashtir / replace "X" with "Y" / замени «X» на «Y»."""
    quotes = quoted(text)
    if len(quotes) < 2 or not _REPLACE_VERB.search(normalize(text)):
        return None
    return quotes[0], quotes[1]


@dataclass(slots=True)
class DocxSource:
    title: str
    filename: str
    data: bytes
    document: KnowledgeDocument | None = None
    artifact: Artifact | None = None
    version: int | None = None

    def provenance(self) -> dict[str, Any]:
        return {
            "kind": "document" if self.document is not None else "artifact",
            "id": str((self.document or self.artifact).id),  # type: ignore[union-attr]
            "title": self.title,
            "version": self.version,
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "size": len(self.data),
        }

    def reference(self) -> dict[str, Any]:
        if self.document is not None:
            return {"kind": "file", "document_id": str(self.document.id), "title": self.title}
        assert self.artifact is not None
        return {
            "kind": "artifact",
            "artifact_id": str(self.artifact.id),
            "version": self.version,
            "title": self.title,
        }


def _is_docx(filename: str, mime: str) -> bool:
    return mime == DOCX_MIME or filename.lower().endswith(".docx")


async def docx_from_document(tools: ToolContext, document: KnowledgeDocument) -> DocxSource | None:
    if not document.storage_key or not _is_docx(document.filename or "", document.mime_type):
        return None
    data = await tools.services.storage.get(document.storage_key)
    return DocxSource(document.title, document.filename or "document.docx", data, document=document)


async def docx_from_artifact(tools: ToolContext, artifact: Artifact) -> DocxSource | None:
    version = await tools.services.artifacts.current_version(tools.session, artifact)
    if version is None or not version.filename.lower().endswith(".docx"):
        return None
    data = await tools.services.artifacts.read(version)
    return DocxSource(
        artifact.title, version.filename, data, artifact=artifact, version=version.version_number
    )


async def find_docx(ctx: GatherContext, document: KnowledgeDocument | None) -> DocxSource | None:
    """The Word file a request is about: attached → the one the agent matched → EZO's
    latest .docx in this conversation."""
    tools = ctx.tools
    for attached in await attached_files(tools, ctx.turn.attachments):
        found = await docx_from_document(tools, attached)
        if found is not None:
            return found
    if document is not None:
        return await docx_from_document(tools, document)
    own = await latest_artifact(
        tools.session, tools.user_id, tools.conversation_id, ("document", "report")
    )
    return await docx_from_artifact(tools, own) if own is not None else None


# --------------------------------------------------------------------------- model editing


@dataclass(slots=True)
class ModelEdit:
    edits: dict[int, str] = field(default_factory=dict)
    missing: list[int] = field(default_factory=list)
    calls: int = 0
    provider: str | None = None
    model: str | None = None
    truncated_batches: int = 0


def _batches(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    batches: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    size = 0
    for index, text in lines:
        if current and (size + len(text) > BATCH_CHARS or len(current) >= BATCH_PARAGRAPHS):
            batches.append(current)
            current, size = [], 0
        current.append((index, text))
        size += len(text) + 10
    if current:
        batches.append(current)
    return batches


def parse_reply(reply: str, allowed: set[int]) -> dict[int, str]:
    edits: dict[int, str] = {}
    last: int | None = None
    for line in reply.splitlines():
        match = _LINE.match(line)
        if match:
            index = int(match.group(1))
            last = index if index in allowed else None
            if last is not None:
                edits[last] = match.group(2).rstrip()
        elif last is not None and line.strip() and not line.strip().startswith("```"):
            edits[last] += " " + line.strip()  # a wrapped line belongs to the same paragraph
    return edits


async def edit_with_model(
    ctx: GatherContext,
    gathered: Gathered,
    lines: list[tuple[int, str]],
    task: str,
    *,
    every_paragraph: bool,
) -> ModelEdit:
    tools = ctx.tools
    result = ModelEdit()
    coverage = (
        "one line for EVERY input paragraph"
        if every_paragraph
        else "only for the paragraphs you change (leave out unchanged ones)"
    )
    system = DOCX_EDIT_SYSTEM.replace("{task}", task).replace("{coverage}", coverage)

    async def run(batch: list[tuple[int, str]]) -> dict[int, str]:
        prompt = "\n".join(f"[[{i}]] {text}" for i, text in batch)
        chars = sum(len(t) for _, t in batch)
        completion = await complete(
            tools.services.router,
            "chat",
            system=system,
            messages=[ChatMessage("user", f"User's request: {ctx.turn.text}\n\n{prompt}")],
            max_output_tokens=min(16_000, int(chars / 2) + 1_500),
            language=ctx.turn.language,
        )
        result.calls += 1
        result.provider, result.model = completion.provider, completion.model
        if completion.truncated:
            result.truncated_batches += 1
        gathered.tool_calls.append(
            completion.trace("edit_docx_paragraphs", f"{len(batch)} paragraphs")
        )
        return parse_reply(completion.text, {i for i, _ in batch})

    batches = _batches(lines)
    for batch in batches:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        result.edits.update(await run(batch))
        if every_paragraph:
            missing = [(i, t) for i, t in batch if i not in result.edits]
            if missing:  # one retry for paragraphs the model left out
                result.edits.update(await run(missing))
    if every_paragraph:
        result.missing = [i for i, _ in lines if i not in result.edits]
    return result


async def transform_docx(
    ctx: GatherContext,
    gathered: Gathered,
    source: DocxSource,
    *,
    transform: str,
    task: str,
    label: str,
    target_language: str | None,
) -> None:
    """Edit `source` in place with the model and store the result (new artifact for an
    upload, new version for EZO's own document)."""
    started = time.monotonic()
    try:
        document = await asyncio.to_thread(fidelity.open_docx, source.data)
        units = fidelity.editable_units(document)
    except DocxEditError as exc:
        gathered.notes.append(f"The Word file could not be edited: {exc.message} Say so.")
        return
    lines = [
        (u.index, u.encode()[0])
        for u in units
        if not u.protected and re.search(r"[^\W\d_]", u.text)
    ]
    total_chars = sum(len(t) for _, t in lines)
    if not lines:
        gathered.notes.append("The Word file has no editable text. Nothing was changed; say so.")
        return
    if total_chars > MAX_EDIT_CHARS:
        gathered.notes.append(
            f"The Word file has {total_chars:,} characters of text, more than EZO edits in one "
            f"request ({MAX_EDIT_CHARS:,}). Nothing was changed and nothing was cut off. Suggest "
            "splitting the document or naming the sections to edit."
        )
        return
    edited = await edit_with_model(
        ctx, gathered, lines, task, every_paragraph=transform == "translate"
    )
    tracked = wants_tracked_changes(ctx.turn.text)
    before = await asyncio.to_thread(fidelity.inventory, source.data)
    data, report = await asyncio.to_thread(
        fidelity.apply_edits, source.data, edited.edits, tracked=tracked
    )
    after = await asyncio.to_thread(fidelity.inventory, data)
    preserved, changed = fidelity.compare_inventory(before, after)
    warnings = list(report.warnings)
    if edited.missing:
        warnings.append(
            f"{len(edited.missing)} paragraph(s) came back without a translation and were left "
            "in the original language."
        )
    if edited.truncated_batches:
        warnings.append(f"{edited.truncated_batches} batch(es) hit the model's output limit.")
    if report.number_changes and transform != "rewrite":
        warnings.append(
            f"Numbers differ from the original in {len(report.number_changes)} paragraph(s); "
            "check them."
        )
    if changed:
        warnings.append("These document properties changed unexpectedly: " + ", ".join(changed))
    if not report.changed:
        gathered.notes.append(
            "The model proposed no changes to the Word file, so no new file was saved. Say so."
        )
        return
    stem = file_stem(source.filename.rsplit(".", 1)[0], "document")
    suffix = {"translate": f" ({target_language})" if target_language else " (translated)"}.get(
        transform, f" ({label.lower()})"
    )
    meta = {
        "action": transform,
        "fidelity": "in_place",
        "tracked_changes": tracked,
        "tracked_changes_granularity": "word-level for uniformly formatted paragraphs, "
        "paragraph-level otherwise"
        if tracked
        else None,
        "inputs": [source.provenance()],
        "edit": report.summary(),
        "paragraphs_sent": len(lines),
        "model_calls": edited.calls,
        "preserved": preserved,
        "changed_properties": changed,
        "inventory": {k: v for k, v in after.items() if k != "page_setup"},
        "warnings": warnings,
        "duration_ms": round((time.monotonic() - started) * 1000),
        **({"target_language": target_language} if target_language else {}),
    }
    text = await asyncio.to_thread(fidelity.docx_text, data)
    exports = {"markdown": (f"{stem}.md", text.encode("utf-8"))}
    artifacts = ctx.tools.services.artifacts
    tools = ctx.tools
    summary = label + (" (tracked changes)" if tracked else "")
    if source.artifact is not None:
        created = await artifacts.add_version(
            tools.session,
            source.artifact,
            filename=source.filename,
            data=data,
            created_by="document",
            provider=edited.provider,
            model=edited.model,
            generation_metadata=meta,
            source_references=[source.reference()],
            change_summary=summary,
            exports=exports,
        )
    else:
        created = await artifacts.create(
            tools.session,
            tools.user_id,
            title=f"{source.title}{suffix}",
            artifact_type="document",
            filename=f"{stem}{suffix}.docx",
            data=data,
            project_id=tools.project_scope,
            conversation_id=tools.conversation_id,
            created_by_agent="document",
            provider=edited.provider,
            model=edited.model,
            generation_metadata=meta,
            source_references=[source.reference()],
            exports=exports,
            change_summary=summary,
        )
    gathered.artifacts.append(artifact_entry(created))
    where = (
        f"a new version (v{created.version.version_number}) of “{source.title}”"
        if source.artifact is not None
        else f"a new Word file “{source.title}{suffix}” (the original upload is unchanged)"
    )
    lines_out = [
        f"{label} done IN THE ORIGINAL WORD FILE, saved as {where}.",
        f"- Paragraphs changed: {len(report.changed)} of {len(lines)} sent"
        + (", recorded as Word tracked changes (author EZO)" if tracked else "")
        + ".",
        "- Kept as in the original (checked after saving): "
        + ", ".join(p.replace("_", " ") for p in preserved if p != "styles_sha256")
        + (", styles" if "styles_sha256" in preserved else "")
        + ".",
        *[f"- WARNING: {w}" for w in warnings],
        "Describe this briefly; do not paste the document. Never invent links.",
    ]
    gathered.notes.append("\n".join(lines_out))


# --------------------------------------------------------------------------- find/replace


async def run_replace_action(ctx: GatherContext, gathered: Gathered) -> bool:
    """«X» ni «Y» ga almashtir — in a Word file, without a model."""
    request = replacement_request(ctx.turn.text)
    if request is None:
        return False
    source = await find_docx(ctx, None)
    if source is None:
        return False  # not about a Word file: let the other actions handle it
    old, new = request
    tracked = wants_tracked_changes(ctx.turn.text)
    try:
        data, report, count = await asyncio.to_thread(
            fidelity.replace_text, source.data, old, new, tracked=tracked
        )
    except DocxEditError as exc:
        gathered.notes.append(f"The Word file could not be edited: {exc.message} Say so.")
        return True
    if count == 0:
        gathered.notes.append(
            f"“{old}” does not occur in “{source.title}”. Nothing was changed; say so exactly."
        )
        return True
    before = await asyncio.to_thread(fidelity.inventory, source.data)
    after = await asyncio.to_thread(fidelity.inventory, data)
    preserved, changed = fidelity.compare_inventory(before, after)
    meta = {
        "action": "replace",
        "fidelity": "in_place",
        "find": old,
        "replace": new,
        "replacements": count,
        "tracked_changes": tracked,
        "inputs": [source.provenance()],
        "edit": report.summary(),
        "preserved": preserved,
        "changed_properties": changed,
        "engine": "python-docx (no AI model)",
    }
    tools = ctx.tools
    stem = file_stem(source.filename.rsplit(".", 1)[0], "document")
    text = await asyncio.to_thread(fidelity.docx_text, data)
    exports = {"markdown": (f"{stem}.md", text.encode("utf-8"))}
    summary = f"Replaced “{old}” with “{new}” ({count}×)"
    if source.artifact is not None:
        created = await tools.services.artifacts.add_version(
            tools.session,
            source.artifact,
            filename=source.filename,
            data=data,
            created_by="document",
            generation_metadata=meta,
            source_references=[source.reference()],
            change_summary=summary,
            exports=exports,
        )
    else:
        created = await tools.services.artifacts.create(
            tools.session,
            tools.user_id,
            title=f"{source.title} (edited)",
            artifact_type="document",
            filename=f"{stem} (edited).docx",
            data=data,
            project_id=tools.project_scope,
            conversation_id=tools.conversation_id,
            created_by_agent="document",
            generation_metadata=meta,
            source_references=[source.reference()],
            exports=exports,
            change_summary=summary,
        )
    gathered.artifacts.append(artifact_entry(created))
    skipped = report.summary()["skipped_paragraphs"]
    gathered.notes.append(
        f"Replaced “{old}” with “{new}” {count} time(s) in the original Word file, locally "
        f"without an AI model{' as tracked changes' if tracked else ''}; formatting kept "
        f"({', '.join(p for p in preserved if p != 'styles_sha256')})."
        + (f" Not changed (protected content): {skipped}." if skipped else "")
        + (" The original upload is unchanged." if source.document is not None else "")
    )
    return True
