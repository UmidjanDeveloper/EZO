"""The `pdf_tool`: deterministic PDF operations on the user's files → new artifacts.

No model and no API key: merging, page edits, rotation, numbering, watermarks,
compression, metadata cleaning, splitting and page images all run locally. Inputs are
the user's uploaded files or EZO artifacts (ownership checked); they are never
modified. Every output is reopened and verified before it is stored, and its
generation metadata records the operation, the inputs (with content hashes), the
verification result, warnings and timing.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import Artifact, KnowledgeDocument
from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.documents.pdf.plan import PlanResult, run_plan
from ezo_api.documents.pdf.requests import PdfStep
from ezo_api.storage.base import StorageError
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.document_tools import artifact_entry, file_stem

MAX_TOTAL_INPUT = 200 * 1024 * 1024
PREVIEW_PAGES = 6
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


class FileRef(BaseModel):
    kind: Literal["document", "artifact"]
    id: uuid.UUID


class PdfToolArgs(BaseModel):
    inputs: list[FileRef] = Field(min_length=1, max_length=20)
    steps: list[PdfStep] = Field(min_length=1, max_length=12)
    title: str = Field(default="", max_length=200)


@dataclass(slots=True)
class LoadedFile:
    ref: FileRef
    title: str
    data: bytes
    mime_type: str
    version: int | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def provenance(self) -> dict[str, Any]:
        return {
            "kind": self.ref.kind,
            "id": str(self.ref.id),
            "title": self.title,
            "version": self.version,
            "sha256": self.sha256,
            "size": len(self.data),
            "mime_type": self.mime_type,
        }

    def source_reference(self) -> dict[str, Any]:
        if self.ref.kind == "document":
            return {"kind": "file", "document_id": str(self.ref.id), "title": self.title}
        return {
            "kind": "artifact",
            "artifact_id": str(self.ref.id),
            "version": self.version,
            "title": self.title,
        }


async def load_file(ctx: ToolContext, ref: FileRef) -> LoadedFile:
    """Read one of the user's files (an upload or the current version of an artifact)."""
    if ref.kind == "document":
        document = await ctx.session.get(KnowledgeDocument, ref.id)
        if document is None or document.user_id != ctx.user_id or not document.storage_key:
            raise ArtifactError("not_found", "A file to work on was not found.")
        try:
            data = await ctx.services.storage.get(document.storage_key)
        except StorageError as exc:
            raise ArtifactError(
                "missing_file", f"The stored file “{document.title}” is missing."
            ) from exc
        return LoadedFile(ref, document.filename or document.title, data, document.mime_type)
    artifact = await ctx.session.get(Artifact, ref.id)
    if artifact is None or artifact.user_id != ctx.user_id:
        raise ArtifactError("not_found", "A file to work on was not found.")
    version = await ctx.services.artifacts.current_version(ctx.session, artifact)
    if version is None:
        raise ArtifactError("not_found", f"“{artifact.title}” has no content yet.")
    data = await ctx.services.artifacts.read(version)
    return LoadedFile(ref, artifact.title, data, version.mime_type, version.version_number)


def _is_pdf(file: LoadedFile) -> bool:
    return file.mime_type.startswith("application/pdf") or file.data[:5] == b"%PDF-"


def _previews(data: bytes, pages: int, stem: str) -> dict[str, tuple[str, bytes]]:
    try:
        images = engine.render_pages(data, list(range(1, min(pages, PREVIEW_PAGES) + 1)), dpi=60)
    except PdfError:
        return {}
    return {f"preview-{n}": (f"{stem}-page-{n}.png", png) for n, png in enumerate(images, start=1)}


class PdfTool(Tool[PdfToolArgs]):
    name: ClassVar[str] = "pdf_tool"
    activity: ClassVar[str] = "working"
    timeout_seconds: ClassVar[float] = 180.0
    description: ClassVar[str] = (
        "Run PDF operations (merge, delete/extract/move/rotate pages, split, page numbers, "
        "watermark, header/footer, compress, clean metadata, images↔PDF, inspect) locally "
        "and store the verified result as new artifacts. No AI model is used."
    )
    args_model: ClassVar[type[BaseModel]] = PdfToolArgs

    async def run(self, args: PdfToolArgs, ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            files = [await load_file(ctx, ref) for ref in args.inputs]
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        if sum(len(f.data) for f in files) > MAX_TOTAL_INPUT:
            return ToolResult(
                ok=False, summary="", error="The files are too large to process together."
            )
        pdfs = [f for f in files if _is_pdf(f)]
        images = [f for f in files if f.mime_type in IMAGE_TYPES]
        unsupported = [f.title for f in files if f not in pdfs and f not in images]
        if unsupported:
            return ToolResult(
                ok=False,
                summary="",
                error=f"Only PDF files and images can be used here, not: {', '.join(unsupported)}.",
                data={"error_kind": "unsupported"},
            )
        try:
            result: PlanResult = await asyncio.to_thread(
                run_plan,
                [f.data for f in pdfs],
                args.steps,
                images=[f.data for f in images] or None,
            )
        except PdfError as exc:
            return ToolResult(
                ok=False, summary="", error=exc.message, data={"error_kind": exc.code}
            )
        duration = round((time.monotonic() - started) * 1000)
        if result.inspected is not None:
            info = result.inspected
            data = {
                "inspected": {
                    "pages": info.page_count,
                    "text_layer": info.text_layer,
                    "scanned_pages": info.scanned_pages[:100],
                    "encrypted": info.encrypted,
                    "signed": info.signed,
                    "has_forms": info.has_forms,
                    "metadata": info.metadata,
                    "size": info.size,
                },
                "report": result.report,
                "warnings": result.warnings,
            }
            return ToolResult(
                ok=True, summary=f"{info.page_count} pages, text layer {info.text_layer}", data=data
            )
        try:
            artifacts = await self._store(ctx, args, files, result, duration)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        return ToolResult(
            ok=True,
            summary=f"{len(artifacts)} file(s): " + "; ".join(result.report)[:300],
            data={
                "artifacts": artifacts,
                "report": result.report,
                "warnings": result.warnings,
                "pages": [o.pages for o in result.outputs if o.kind == "pdf"],
                "duration_ms": duration,
            },
        )

    async def _store(
        self,
        ctx: ToolContext,
        args: PdfToolArgs,
        files: list[LoadedFile],
        result: PlanResult,
        duration: int,
    ) -> list[dict[str, Any]]:
        title = args.title or (files[0].title.rsplit(".", 1)[0] if files else "PDF")
        base = {
            "operation": "pdf",
            "steps": [s.model_dump(exclude_none=True) for s in args.steps],
            "inputs": [f.provenance() for f in files],
            "report": result.report,
            "warnings": result.warnings,
            "engine": "pypdf + pypdfium2 (local, no AI model)",
            "duration_ms": duration,
            "page_numbering": "page references count pages of the input (after merging)",
        }
        references = [f.source_reference() for f in files]
        outputs = result.outputs
        stored: list[dict[str, Any]] = []
        if outputs and outputs[0].kind == "png":
            stem = file_stem(title, "pages")
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
                for output in outputs:
                    zipped.writestr(f"{stem}-{output.label}.png", output.data)
            exports = {
                f"preview-{n}": (f"{stem}-{o.label}.png", o.data)
                for n, o in enumerate(outputs[:24], start=1)
            }
            meta = {
                **base,
                "output": {"images": len(outputs), "format": "png"},
                "verification": {"images": len(outputs)},
            }
            created = await ctx.services.artifacts.create(
                ctx.session,
                ctx.user_id,
                title=f"{title} — PNG",
                artifact_type="other",
                filename=f"{stem}-pages.zip",
                data=archive.getvalue(),
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="document",
                generation_metadata=meta,
                source_references=references,
                exports=exports,
                change_summary="Created",
            )
            return [artifact_entry(created)]
        for index, output in enumerate(outputs, start=1):
            label = title if len(outputs) == 1 else f"{title} ({index})"
            stem = file_stem(label, "document")
            pages = engine.verify_pdf(output.data, output.pages)
            meta = {
                **base,
                "output": {
                    "sha256": hashlib.sha256(output.data).hexdigest(),
                    "size": len(output.data),
                    "pages": pages,
                    "part": index if len(outputs) > 1 else None,
                },
                "verification": {
                    "reopened": True,
                    "page_count": pages,
                    "expected_pages": output.pages,
                },
            }
            created = await ctx.services.artifacts.create(
                ctx.session,
                ctx.user_id,
                title=label,
                artifact_type="document",
                filename=f"{stem}.pdf",
                data=output.data,
                project_id=ctx.project_scope,
                conversation_id=ctx.conversation_id,
                created_by_agent="document",
                generation_metadata=meta,
                source_references=references,
                exports=await asyncio.to_thread(_previews, output.data, pages, stem),
                change_summary="Created",
            )
            stored.append(artifact_entry(created))
        return stored
