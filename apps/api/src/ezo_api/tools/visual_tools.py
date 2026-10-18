"""Tools that create and edit image artifacts.

Every result is a versioned image artifact (PNG) with a small preview and a
``spec`` export that records what was asked, so a later edit can build on it.
Generation metadata stores provider, model, prompt, dimensions and, for
placeholders, the fact that no generated picture is inside.

Images are paid provider calls: the VisualService enforces EZO's limits, and a
provider's refusal is final (EZO never retries the request elsewhere).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError

from ezo_api.artifacts.service import ArtifactError, VersionResult
from ezo_api.db.models import Artifact, ArtifactVersion, KnowledgeDocument
from ezo_api.storage.base import StorageError
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.document_tools import artifact_entry, file_stem, owned_artifact
from ezo_api.visual.base import ASPECT_RATIOS, aspect_value
from ezo_api.visual.compose import (
    SOCIAL_FORMATS,
    Composed,
    DiagramSpec,
    LogoSpec,
    SocialSpec,
    compose_diagram,
    compose_logo,
    compose_social,
)
from ezo_api.visual.images import ImageRejectedError, normalize_image, thumbnail
from ezo_api.visual.service import AllImageProvidersFailedError, ImageOutcome

ImageKind = Literal["image", "hero", "product", "presentation"]
Aspect = Literal["1:1", "4:3", "3:4", "16:9", "9:16", "4:5", "3:2", "2:3"]


def nearest_aspect(width: int, height: int) -> str:
    ratio = width / height
    return min(ASPECT_RATIOS, key=lambda a: abs(aspect_value(a) - ratio))


def _attempts(outcome: ImageOutcome | AllImageProvidersFailedError) -> list[dict[str, Any]]:
    return [
        {"provider": a.provider, "model": a.model, "ok": a.ok, "error": a.kind}
        for a in outcome.attempts
    ]


def _failure(exc: AllImageProvidersFailedError) -> ToolResult:
    kind = "refused" if exc.refused else "failed"
    return ToolResult(
        ok=False,
        summary="",
        error=exc.message,
        data={"error_kind": kind, "attempts": _attempts(exc)},
    )


def _spec_json(spec: dict[str, Any]) -> bytes:
    return json.dumps(spec, ensure_ascii=False, indent=1).encode()


async def _store(
    ctx: ToolContext,
    *,
    existing: Artifact | None,
    title: str,
    png: bytes,
    exports: dict[str, tuple[str, bytes]],
    provider: str | None,
    model: str | None,
    metadata: dict[str, Any],
    artifact_meta: dict[str, Any],
    change_summary: str,
    source_references: list[dict[str, Any]] | None = None,
) -> VersionResult:
    stem = file_stem(title, "image")
    exports = {"preview-1": (f"{stem}-preview.png", thumbnail(png)), **exports}
    if existing is None:
        return await ctx.services.artifacts.create(
            ctx.session,
            ctx.user_id,
            title=title,
            artifact_type="image",
            filename=f"{stem}.png",
            data=png,
            project_id=ctx.project_scope,
            conversation_id=ctx.conversation_id,
            created_by_agent="visual",
            provider=provider,
            model=model,
            metadata=artifact_meta,
            generation_metadata=metadata,
            source_references=source_references,
            exports=exports,
        )
    existing.meta = {**(existing.meta or {}), **artifact_meta}
    return await ctx.services.artifacts.add_version(
        ctx.session,
        existing,
        filename=f"{stem}.png",
        data=png,
        created_by="agent:visual",
        provider=provider,
        model=model,
        generation_metadata=metadata,
        source_references=source_references,
        change_summary=change_summary,
        exports=exports,
    )


def _reported(result: VersionResult, **extra: Any) -> dict[str, Any]:
    return {"artifact": artifact_entry(result), **extra}


# --- generate_image --------------------------------------------------------------------------


class GenerateImageArgs(BaseModel):
    prompt: str = Field(min_length=3, max_length=4_000)
    title: str = Field(default="Image", max_length=200)
    kind: ImageKind = "image"
    aspect_ratio: Aspect = "1:1"
    alt_text: str = Field(default="", max_length=500)
    artifact_id: uuid.UUID | None = Field(
        default=None, description="Regenerate as a new version of this image artifact"
    )
    used_in: str = Field(default="", max_length=300, description="e.g. the deck it belongs to")


class GenerateImageTool(Tool[GenerateImageArgs]):
    name: ClassVar[str] = "generate_image"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 240.0
    description: ClassVar[str] = (
        "Generate an image with the configured image provider and store it as a versioned "
        "image artifact (provider, model, prompt and dimensions recorded)."
    )
    args_model: ClassVar[type[BaseModel]] = GenerateImageArgs

    async def run(self, args: GenerateImageArgs, ctx: ToolContext) -> ToolResult:
        visual = ctx.services.visual
        if not visual.can_generate:
            return ToolResult(
                ok=False,
                summary="",
                error="No image provider is configured.",
                data={"error_kind": "unavailable"},
            )
        try:
            existing = await owned_artifact(ctx, args.artifact_id, ("image",))
            outcome = await visual.generate(args.prompt, args.aspect_ratio)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        except AllImageProvidersFailedError as exc:
            return _failure(exc)
        image = outcome.image
        spec = {"kind": args.kind, "prompt": args.prompt, "aspect_ratio": args.aspect_ratio}
        metadata = {
            **spec,
            "provider": outcome.provider,
            "model": outcome.model,
            "revised_prompt": outcome.revised_prompt,
            "width": image.width,
            "height": image.height,
            "quality": visual.quality,
            "alt_text": args.alt_text,
            "placeholder": False,
            "attempts": _attempts(outcome),
        }
        if args.used_in:
            metadata["used_in"] = args.used_in
        stem = file_stem(args.title, "image")
        try:
            result = await _store(
                ctx,
                existing=existing,
                title=args.title,
                png=image.data,
                exports={"spec": (f"{stem}.json", _spec_json(spec))},
                provider=outcome.provider,
                model=outcome.model,
                metadata=metadata,
                artifact_meta={"kind": args.kind, "placeholder": False},
                change_summary="Regenerated",
            )
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        return ToolResult(
            ok=True,
            summary=f"{args.title}: {image.width}×{image.height} "
            f"({outcome.provider}/{outcome.model})",
            data=_reported(
                result,
                provider=outcome.provider,
                model=outcome.model,
                width=image.width,
                height=image.height,
            ),
        )


# --- edit_image ------------------------------------------------------------------------------


class EditImageArgs(BaseModel):
    instruction: str = Field(min_length=3, max_length=4_000)
    artifact_id: uuid.UUID | None = Field(default=None, description="An image artifact to edit")
    document_id: uuid.UUID | None = Field(default=None, description="An uploaded image to edit")
    title: str = Field(default="", max_length=200)
    change_summary: str = Field(default="", max_length=500)


async def _source_image(
    ctx: ToolContext, args: EditImageArgs
) -> tuple[bytes, Artifact | None, KnowledgeDocument | None]:
    if args.artifact_id is not None:
        artifact = await owned_artifact(ctx, args.artifact_id, ("image",))
        assert artifact is not None
        version = await ctx.services.artifacts.current_version(ctx.session, artifact)
        if version is None:
            raise ArtifactError("not_found", "The image has no content yet.")
        return await ctx.services.artifacts.read(version), artifact, None
    if args.document_id is not None:
        document = await ctx.session.get(KnowledgeDocument, args.document_id)
        if (
            document is None
            or document.user_id != ctx.user_id
            or not document.mime_type.startswith("image/")
            or not document.storage_key
        ):
            raise ArtifactError("not_found", "The image to edit does not exist.")
        try:
            return await ctx.services.storage.get(document.storage_key), None, document
        except StorageError as exc:
            raise ArtifactError("missing_file", "The uploaded image file is missing.") from exc
    raise ArtifactError("invalid", "Name the image to edit.")


class EditImageTool(Tool[EditImageArgs]):
    name: ClassVar[str] = "edit_image"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 240.0
    description: ClassVar[str] = (
        "Edit an image artifact (new version) or an uploaded image (new artifact) with the "
        "configured image provider."
    )
    args_model: ClassVar[type[BaseModel]] = EditImageArgs

    async def run(self, args: EditImageArgs, ctx: ToolContext) -> ToolResult:
        visual = ctx.services.visual
        if not visual.can_edit:
            return ToolResult(
                ok=False,
                summary="",
                error="No image provider that can edit images is configured.",
                data={"error_kind": "unavailable"},
            )
        try:
            original, artifact, document = await _source_image(ctx, args)
            clean = normalize_image(original)  # an untrusted upload is re-encoded first
            aspect = nearest_aspect(clean.width, clean.height)
            outcome = await visual.edit(clean.data, "image/png", args.instruction, aspect)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        except ImageRejectedError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        except AllImageProvidersFailedError as exc:
            return _failure(exc)
        image = outcome.image
        title = args.title or (
            artifact.title if artifact else f"{document.title if document else 'Image'} (edited)"
        )
        spec = {"kind": "image", "prompt": args.instruction, "aspect_ratio": aspect, "edit": True}
        references = (
            [
                {
                    "kind": "file",
                    "document_id": str(document.id),
                    "title": document.title,
                    "source_name": document.filename or document.title,
                }
            ]
            if document
            else None
        )
        metadata = {
            **spec,
            "provider": outcome.provider,
            "model": outcome.model,
            "width": image.width,
            "height": image.height,
            "quality": visual.quality,
            "placeholder": False,
            "attempts": _attempts(outcome),
        }
        stem = file_stem(title, "image")
        try:
            result = await _store(
                ctx,
                existing=artifact,
                title=title,
                png=image.data,
                exports={"spec": (f"{stem}.json", _spec_json(spec))},
                provider=outcome.provider,
                model=outcome.model,
                metadata=metadata,
                artifact_meta={"kind": (artifact.meta or {}).get("kind", "image")}
                if artifact
                else {"kind": "image", "placeholder": False},
                change_summary=args.change_summary or "Edited",
                source_references=references,
            )
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        return ToolResult(
            ok=True,
            summary=f"{title}: edited, {image.width}×{image.height} ({outcome.provider})",
            data=_reported(
                result,
                provider=outcome.provider,
                model=outcome.model,
                width=image.width,
                height=image.height,
                edited_version=result.version.version_number,
            ),
        )


# --- create_graphic --------------------------------------------------------------------------


class CreateGraphicArgs(BaseModel):
    kind: Literal["diagram", "social", "logo"]
    spec: dict[str, Any]
    title: str = Field(default="", max_length=200)
    language: Literal["uz", "en", "ru"] = "uz"
    artifact_id: uuid.UUID | None = Field(
        default=None, description="Add a new version to this graphic"
    )
    picture_instruction: str = Field(
        default="",
        max_length=2_000,
        description="Change the existing picture (background/symbol) of the graphic this way",
    )
    change_summary: str = Field(default="", max_length=500)


async def _previous_picture(ctx: ToolContext, artifact: Artifact | None) -> bytes | None:
    if artifact is None:
        return None
    version: ArtifactVersion | None = await ctx.services.artifacts.current_version(
        ctx.session, artifact
    )
    if version is None:
        return None
    try:
        _, data = await ctx.services.artifacts.read_export(version, "picture")
    except ArtifactError:
        return None
    return data


class CreateGraphicTool(Tool[CreateGraphicArgs]):
    name: ClassVar[str] = "create_graphic"
    activity: ClassVar[str] = "creating"
    timeout_seconds: ClassVar[float] = 240.0
    description: ClassVar[str] = (
        "Lay out a diagram, social graphic or logo concept sheet with EZO's own text "
        "rendering; the picture comes from the image provider when one is configured, "
        "otherwise an abstract placeholder is used and recorded as such."
    )
    args_model: ClassVar[type[BaseModel]] = CreateGraphicArgs

    async def run(self, args: CreateGraphicArgs, ctx: ToolContext) -> ToolResult:
        try:
            return await self._run(args, ctx)
        except ArtifactError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        except ValidationError as exc:
            return ToolResult(ok=False, summary="", error=f"Invalid spec: {exc.errors()[:2]}")

    async def _picture(
        self,
        ctx: ToolContext,
        args: CreateGraphicArgs,
        existing: Artifact | None,
        prompt: str,
        aspect: str,
    ) -> tuple[bytes | None, ImageOutcome | None, str | None]:
        """The picture to use, the provider outcome, and why it is a placeholder (if it is)."""
        visual = ctx.services.visual
        previous = await _previous_picture(ctx, existing)
        try:
            if previous is not None and args.picture_instruction:
                if not visual.can_edit:
                    return previous, None, None
                outcome = await visual.edit(previous, "image/png", args.picture_instruction, aspect)
                return outcome.image.data, outcome, None
            if previous is not None:
                return previous, None, None
            if not prompt:
                return None, None, "no picture was requested"
            if not visual.can_generate:
                return None, None, "no image provider is configured"
            outcome = await visual.generate(prompt, aspect)
            return outcome.image.data, outcome, None
        except AllImageProvidersFailedError as exc:
            reason = "the image service declined the picture" if exc.refused else exc.message
            return previous, None, None if previous else reason

    async def _run(self, args: CreateGraphicArgs, ctx: ToolContext) -> ToolResult:
        existing = await owned_artifact(ctx, args.artifact_id, ("image",))
        picture: bytes | None = None
        outcome: ImageOutcome | None = None
        reason: str | None = None
        composed: Composed
        if args.kind == "diagram":
            diagram = DiagramSpec.model_validate(args.spec)
            composed = await asyncio.to_thread(compose_diagram, diagram, args.language)
            spec: dict[str, Any] = diagram.model_dump(mode="json")
            title = args.title or diagram.title or "Diagram"
            prompt = ""
        elif args.kind == "social":
            social = SocialSpec.model_validate(args.spec)
            aspect = SOCIAL_FORMATS[social.format][2]
            prompt = social.image_prompt
            picture, outcome, reason = await self._picture(ctx, args, existing, prompt, aspect)
            composed = await asyncio.to_thread(compose_social, social, picture)
            spec = social.model_dump(mode="json")
            title = args.title or social.headline
        else:
            logo = LogoSpec.model_validate(args.spec)
            prompt = logo.symbol_prompt
            picture, outcome, reason = await self._picture(ctx, args, existing, prompt, "1:1")
            composed = await asyncio.to_thread(compose_logo, logo, picture)
            spec = logo.model_dump(mode="json")
            title = args.title or f"{logo.brand} — logo"

        placeholder = args.kind != "diagram" and picture is None
        stem = file_stem(title, args.kind)
        exports: dict[str, tuple[str, bytes]] = {
            "spec": (f"{stem}.json", _spec_json({"kind": args.kind, **spec}))
        }
        if composed.svg:
            exports["svg"] = (f"{stem}.svg", composed.svg)
        if picture is not None:
            exports["picture"] = (f"{stem}-picture.png", picture)
        previous_meta = existing.meta if existing else {}
        provider = outcome.provider if outcome else (previous_meta or {}).get("provider")
        model = outcome.model if outcome else (previous_meta or {}).get("model")
        if args.kind == "diagram":
            provider, model = "ezo", "layout-engine"
        metadata = {
            "kind": args.kind,
            "spec": spec,
            "prompt": prompt or None,
            "provider": provider,
            "model": model,
            "width": composed.width,
            "height": composed.height,
            "placeholder": placeholder,
            "placeholder_reason": reason if placeholder else None,
            "text_fits": composed.text_fits,
            "text_rendered_by": "ezo",
        }
        if outcome is not None:
            metadata["attempts"] = _attempts(outcome)
            metadata["revised_prompt"] = outcome.revised_prompt
        result = await _store(
            ctx,
            existing=existing,
            title=title,
            png=composed.png,
            exports=exports,
            provider=provider if args.kind != "diagram" else "ezo",
            model=model,
            metadata=metadata,
            artifact_meta={
                "kind": args.kind,
                "placeholder": placeholder,
                **({"provider": provider, "model": model} if outcome else {}),
            },
            change_summary=args.change_summary or "Edited",
        )
        return ToolResult(
            ok=True,
            summary=f"{title}: {args.kind} {composed.width}×{composed.height}"
            + (" (placeholder picture)" if placeholder else ""),
            data=_reported(
                result,
                kind=args.kind,
                placeholder=placeholder,
                placeholder_reason=reason if placeholder else None,
                provider=provider,
                model=model,
                width=composed.width,
                height=composed.height,
                text_fits=composed.text_fits,
            ),
        )
