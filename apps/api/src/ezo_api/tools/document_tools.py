"""Tools that read the user's files and create document, spreadsheet and presentation artifacts.

The file formats are produced by the format services in ``ezo_api.documents``;
these tools only validate input, call them (off the event loop) and store the
result as an artifact version. Nothing here calls a model.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import Counter
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError

from ezo_api.agents.references import document_text
from ezo_api.artifacts.service import ArtifactError, VersionResult
from ezo_api.db.models import Artifact, KnowledgeDocument, StoryProject
from ezo_api.documents.docx.writer import render_docx
from ezo_api.documents.markdown_io import parse_markdown, to_markdown, to_text
from ezo_api.documents.model import word_count
from ezo_api.documents.pdf.writer import render_pdf
from ezo_api.documents.render.build import DeckBuild, DeckBuildError, build_deck
from ezo_api.documents.render.spec import DeckSpec
from ezo_api.documents.spreadsheet.analysis import describe, read_sheets, summarize_sheet
from ezo_api.documents.spreadsheet.writer import Sheet, render_csv, render_xlsx
from ezo_api.knowledge.uploads import sanitize_filename
from ezo_api.storage.base import StorageError
from ezo_api.story.from_deck import scene_from_slide, story_from_deck
from ezo_api.story.service import StoryError
from ezo_api.tools.base import Tool, ToolContext, ToolResult

MAX_READ_CHARS = 200_000
SPREADSHEET_EXTENSIONS = (".xlsx", ".xls", ".csv")


def file_stem(title: str, fallback: str) -> str:
    stem = sanitize_filename(title, max_length=80).rsplit(".", 1)[0]
    return stem if stem and stem != "file" else fallback


def artifact_entry(result: VersionResult) -> dict[str, Any]:
    """How a created artifact is reported to the turn (shown as a card under the answer)."""
    return {
        "id": str(result.artifact.id),
        "title": result.artifact.title,
        "type": result.artifact.artifact_type,
        "version": result.version.version_number,
    }


async def owned_artifact(
    ctx: ToolContext, artifact_id: uuid.UUID | None, types: tuple[str, ...]
) -> Artifact | None:
    if artifact_id is None:
        return None
    artifact = await ctx.session.get(Artifact, artifact_id)
    if artifact is None or artifact.user_id != ctx.user_id or artifact.artifact_type not in types:
        raise ArtifactError("not_found", "The artifact to update does not exist.")
    return artifact


# --- read_document ---------------------------------------------------------------------------


class ReadDocumentArgs(BaseModel):
    document_id: uuid.UUID
    max_chars: int = Field(default=60_000, ge=1_000, le=MAX_READ_CHARS)


class ReadDocumentTool(Tool[ReadDocumentArgs]):
    name: ClassVar[str] = "read_document"
    activity: ClassVar[str] = "reading"
    description: ClassVar[str] = (
        "Read the extracted text of one of the user's uploaded files; spreadsheets also get "
        "a factual summary of their columns."
    )
    args_model: ClassVar[type[BaseModel]] = ReadDocumentArgs

    async def run(self, args: ReadDocumentArgs, ctx: ToolContext) -> ToolResult:
        document = await ctx.session.get(KnowledgeDocument, args.document_id)
        if (
            document is None
            or document.user_id != ctx.user_id
            or (document.project_id is not None and document.project_id != ctx.project_scope)
        ):
            return ToolResult(ok=False, summary="", error="Document not found.")
        text = await document_text(ctx.session, document)
        data: dict[str, Any] = {
            "id": str(document.id),
            "title": document.title,
            "filename": document.filename,
            "status": document.status,
            "chars": len(text),
            "truncated": len(text) > args.max_chars,
            "text": text[: args.max_chars],
        }
        filename = (document.filename or "").lower()
        if filename.endswith(SPREADSHEET_EXTENSIONS) and document.storage_key:
            try:
                raw = await ctx.services.storage.get(document.storage_key)
                sheets = await asyncio.to_thread(read_sheets, raw, filename)
                data["table_summary"] = describe([summarize_sheet(s) for s in sheets])
            except (StorageError, ValueError, KeyError, OSError) as exc:
                data["table_summary_error"] = type(exc).__name__
        summary = f"{document.title}: {len(text)} characters" + (
            " (spreadsheet summarised)" if "table_summary" in data else ""
        )
        return ToolResult(ok=True, summary=summary, data=data)


# --- create_document -------------------------------------------------------------------------

DocumentFormat = Literal["docx", "pdf", "md", "txt"]
_EXPORT_NAMES = {"docx": "docx", "pdf": "pdf", "md": "markdown"}


class CreateDocumentArgs(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    markdown: str = Field(min_length=1, max_length=1_000_000)
    format: DocumentFormat = "docx"
    artifact_type: Literal["document", "report"] = "document"
    artifact_id: uuid.UUID | None = Field(
        default=None, description="Add a new version to this existing document"
    )
    change_summary: str = Field(default="", max_length=2_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    provider: str | None = None
    model: str | None = None


def render_document(markdown: str, title: str, fmt: DocumentFormat) -> dict[str, bytes]:
    """All formats of one document: {extension: bytes}. The requested one comes first."""
    spec = parse_markdown(markdown, title=title)
    files: dict[str, bytes] = {}
    order = [fmt, *[f for f in ("docx", "pdf", "md") if f != fmt]]
    for extension in order:
        if extension == "docx":
            files["docx"] = render_docx(spec)
        elif extension == "pdf":
            files["pdf"] = render_pdf(spec)
        elif extension == "md":
            files["md"] = to_markdown(spec).encode("utf-8")
        elif extension == "txt":
            files["txt"] = to_text(spec).encode("utf-8")
    return files


class CreateDocumentTool(Tool[CreateDocumentArgs]):
    name: ClassVar[str] = "create_document"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 90.0
    description: ClassVar[str] = (
        "Create a document (DOCX/PDF/Markdown/TXT) from Markdown, or add a new version to an "
        "existing one. Other formats are attached as exports."
    )
    args_model: ClassVar[type[BaseModel]] = CreateDocumentArgs

    async def run(self, args: CreateDocumentArgs, ctx: ToolContext) -> ToolResult:
        try:
            return await self._run(args, ctx)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)

    async def _run(self, args: CreateDocumentArgs, ctx: ToolContext) -> ToolResult:
        artifacts = ctx.services.artifacts
        existing = await owned_artifact(ctx, args.artifact_id, ("document", "report"))
        files = await asyncio.to_thread(render_document, args.markdown, args.title, args.format)
        main_ext = args.format
        stem = file_stem(args.title, "document")
        exports = {
            _EXPORT_NAMES[ext]: (f"{stem}.{ext}", data)
            for ext, data in files.items()
            if ext != main_ext and ext in _EXPORT_NAMES
        }
        spec = parse_markdown(args.markdown, title=args.title)
        metadata = {**args.metadata, "words": word_count(spec), "format": main_ext}
        if existing is None:
            result = await artifacts.create(
                ctx.session,
                ctx.user_id,
                title=args.title,
                artifact_type=args.artifact_type,
                filename=f"{stem}.{main_ext}",
                data=files[main_ext],
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="document",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                source_references=args.source_references,
                exports=exports,
                change_summary=args.change_summary,
            )
        else:
            result = await artifacts.add_version(
                ctx.session,
                existing,
                filename=f"{stem}.{main_ext}",
                data=files[main_ext],
                created_by="agent:document",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                source_references=args.source_references,
                change_summary=args.change_summary or "Edited",
                exports=exports,
            )
        formats = [main_ext, *[ext for ext in files if ext != main_ext]]
        return ToolResult(
            ok=True,
            summary=f"{result.artifact.title} v{result.version.version_number} "
            f"({', '.join(formats)}, {metadata['words']} words)",
            data={
                "artifact": artifact_entry(result),
                "formats": formats,
                "words": metadata["words"],
            },
        )


# --- create_spreadsheet ----------------------------------------------------------------------


class SheetIn(BaseModel):
    name: str = Field(default="Sheet1", max_length=100)
    columns: list[str] = Field(min_length=1, max_length=100)
    rows: list[list[str | float | int | None]] = Field(default_factory=list, max_length=20_000)


class CreateSpreadsheetArgs(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    sheets: list[SheetIn] = Field(min_length=1, max_length=20)
    format: Literal["xlsx", "csv"] = "xlsx"
    artifact_id: uuid.UUID | None = None
    change_summary: str = Field(default="", max_length=2_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None


class CreateSpreadsheetTool(Tool[CreateSpreadsheetArgs]):
    name: ClassVar[str] = "create_spreadsheet"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 60.0
    description: ClassVar[str] = "Create an XLSX (or CSV) spreadsheet artifact from rows."
    args_model: ClassVar[type[BaseModel]] = CreateSpreadsheetArgs

    async def run(self, args: CreateSpreadsheetArgs, ctx: ToolContext) -> ToolResult:
        try:
            return await self._run(args, ctx)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)

    async def _run(self, args: CreateSpreadsheetArgs, ctx: ToolContext) -> ToolResult:
        existing = await owned_artifact(ctx, args.artifact_id, ("spreadsheet",))
        sheets = [Sheet(s.name, s.columns, [list(r) for r in s.rows]) for s in args.sheets]
        stem = file_stem(args.title, "spreadsheet")
        if args.format == "xlsx":
            data = await asyncio.to_thread(render_xlsx, sheets, args.title)
            exports = {"csv": (f"{stem}.csv", render_csv(sheets[0]))} if len(sheets) == 1 else {}
        else:
            data = render_csv(sheets[0])
            exports = {"xlsx": (f"{stem}.xlsx", await asyncio.to_thread(render_xlsx, sheets))}
        rows = sum(len(s.rows) for s in sheets)
        metadata = {**args.metadata, "sheets": len(sheets), "rows": rows}
        filename = f"{stem}.{args.format}"
        if existing is None:
            result = await ctx.services.artifacts.create(
                ctx.session,
                ctx.user_id,
                title=args.title,
                artifact_type="spreadsheet",
                filename=filename,
                data=data,
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="document",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                exports=exports,
            )
        else:
            result = await ctx.services.artifacts.add_version(
                ctx.session,
                existing,
                filename=filename,
                data=data,
                created_by="agent:document",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                change_summary=args.change_summary or "Edited",
                exports=exports,
            )
        return ToolResult(
            ok=True,
            summary=f"{result.artifact.title}: {len(sheets)} sheet(s), {rows} rows",
            data={"artifact": artifact_entry(result), "rows": rows},
        )


# --- create_presentation ---------------------------------------------------------------------


class CreatePresentationArgs(BaseModel):
    deck: dict[str, Any]
    artifact_id: uuid.UUID | None = Field(
        default=None, description="Add a new version to this existing presentation"
    )
    change_summary: str = Field(default="", max_length=2_000)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    provider: str | None = None
    model: str | None = None


def deck_exports(build: DeckBuild, stem: str) -> dict[str, tuple[str, bytes]]:
    exports = {
        "pdf": (f"{stem}.pdf", build.pdf),
        "html": (f"{stem}.html", build.html),
        "spec": (
            f"{stem}.json",
            json.dumps(build.deck.model_dump(mode="json"), ensure_ascii=False, indent=1).encode(),
        ),
    }
    for number, png in enumerate(build.previews, start=1):
        exports[f"preview-{number}"] = (f"{stem}-slide-{number}.png", png)
    return exports


class CreatePresentationTool(Tool[CreatePresentationArgs]):
    name: ClassVar[str] = "create_presentation"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 240.0
    description: ClassVar[str] = (
        "Lay out a presentation spec, run layout QA and export PPTX (+ PDF, web version and "
        "slide previews) as an artifact with a linked story project."
    )
    args_model: ClassVar[type[BaseModel]] = CreatePresentationArgs

    async def run(self, args: CreatePresentationArgs, ctx: ToolContext) -> ToolResult:
        try:
            deck = DeckSpec.model_validate(args.deck)
        except ValidationError as exc:
            return ToolResult(ok=False, summary="", error=f"Invalid deck: {exc.errors()[:2]}")
        try:
            return await self._run(deck, args, ctx)
        except (ArtifactError, StoryError) as exc:
            return ToolResult(ok=False, summary="", error=exc.message)

    async def _run(
        self, deck: DeckSpec, args: CreatePresentationArgs, ctx: ToolContext
    ) -> ToolResult:
        existing = await owned_artifact(ctx, args.artifact_id, ("presentation",))
        try:
            build = await asyncio.to_thread(build_deck, deck)
        except DeckBuildError as exc:
            return ToolResult(ok=False, summary="", error=str(exc))
        stem = file_stem(deck.title, "presentation")
        layouts = Counter(slide.layout for slide in build.deck.slides)
        metadata: dict[str, Any] = {
            "slides": len(build.plans),
            "theme": build.theme.name,
            "aspect_ratio": deck.aspect_ratio,
            "language": deck.language,
            "layouts": dict(layouts),
            "qa": build.qa.to_dict(),
            "fixes": build.fixes,
            "previews": len(build.previews),
        }
        exports = deck_exports(build, stem)
        if existing is None:
            result = await ctx.services.artifacts.create(
                ctx.session,
                ctx.user_id,
                title=deck.title,
                artifact_type="presentation",
                filename=f"{stem}.pptx",
                data=build.pptx,
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="presentation",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                source_references=args.source_references,
                exports=exports,
            )
            story_data = story_from_deck(
                build.deck, theme=build.theme.name, artifact_id=str(result.artifact.id)
            )
            story_data.project_id = ctx.project_scope
            story = await ctx.services.stories.create(ctx.session, ctx.user_id, story_data)
            result.artifact.meta = {**(result.artifact.meta or {}), "story_id": str(story.id)}
        else:
            result = await ctx.services.artifacts.add_version(
                ctx.session,
                existing,
                filename=f"{stem}.pptx",
                data=build.pptx,
                created_by="agent:presentation",
                provider=args.provider,
                model=args.model,
                generation_metadata=metadata,
                source_references=args.source_references,
                change_summary=args.change_summary or "Regenerated",
                exports=exports,
            )
            story_id = (existing.meta or {}).get("story_id")
            linked = await ctx.session.get(StoryProject, uuid.UUID(story_id)) if story_id else None
            if linked is not None and linked.user_id == ctx.user_id:
                story = linked
                story.title = deck.title[:300] or story.title
                story.visual_style = build.theme.name
                await ctx.services.stories.replace_scenes(
                    ctx.session, story, [scene_from_slide(s) for s in build.deck.slides]
                )
        await ctx.session.flush()
        qa = build.qa
        return ToolResult(
            ok=True,
            summary=f"{deck.title}: {len(build.plans)} slides, theme {build.theme.name}, "
            f"QA errors={len(qa.errors)} warnings={qa.to_dict()['warnings']}",
            data={
                "artifact": artifact_entry(result),
                "slides": len(build.plans),
                "theme": build.theme.name,
                "qa": qa.to_dict(),
                "fixes": build.fixes,
                "story_id": (result.artifact.meta or {}).get("story_id"),
            },
        )
