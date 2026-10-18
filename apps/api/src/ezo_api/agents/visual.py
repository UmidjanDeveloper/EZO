# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""VisualAgent: images, edits, diagrams, social graphics and logo concepts.

Workflow (every step is traced; tools are logged):

    kind, aspect ratio and number of variants (rules, uz/en/ru)
    → edit?  an image from this conversation or a recent upload
    → one cheap "chat" model call writes the image prompt / graphic spec as JSON
    → generate_image / edit_image / create_graphic → versioned image artifacts

Honesty: a request that needs a generated picture is not attempted without an
image provider (no model call, nothing stored, the user is told why). Diagrams
never need one, and social graphics / logo sheets fall back to an abstract,
clearly labelled placeholder picture with EZO-rendered text.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import or_, select

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered, call_tool
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.llm import complete, extract_json
from ezo_api.agents.references import latest_artifact
from ezo_api.artifacts.service import ArtifactError
from ezo_api.core.intent import Intent
from ezo_api.db.models import Artifact, KnowledgeDocument
from ezo_api.documents.render.theme import THEMES
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext
from ezo_api.visual.kinds import COMPOSED_KINDS, VisualRequest, detect_request, wants_edit

logger = logging.getLogger(__name__)

PROMPT_RULES = """Image prompt rules (for every "prompt", "image_prompt" and "symbol_prompt"):
- Write it in English, concrete and visual: subject, setting, composition, lighting, colour palette, style, mood.
- NEVER ask for text, letters, words, numbers or logos inside the picture: EZO adds all text itself.
- Do not depict real, identifiable private persons; do not imitate existing brands, trademarks or logos; do not name living artists.
- Keep it under 120 words."""

ITEM_SCHEMAS = {
    "image": '{"title": short title (user\'s language), "prompt": str, "alt_text": one sentence (user\'s language)}',
    "hero": '{"title": str, "prompt": str (a wide website hero visual with calm space for a headline), "alt_text": str}',
    "product": '{"title": str, "prompt": str (a clean product visual: studio light, simple background), "alt_text": str}',
    "social": '{"title": str, "headline": str (max 8 words, user\'s language), "subline": str (max 16 words, optional), "brand": str (optional), "image_prompt": str (a background photo/illustration that supports the message, no text)}',
    "logo": '{"title": str, "brand": str (the exact name the user gave), "tagline": str (optional, max 6 words), "symbol_prompt": str (a simple, flat, vector-style symbol on a plain background, no letters)}',
    "diagram": '{"title": str, "kind": "flow"|"architecture"|"process"|"timeline", "nodes": [{"id": str, "label": str}] (3-8, for flow/architecture), "edges": [[from_id, to_id]], "steps": [{"label": str, "text": str}] (3-6, for process/timeline)}',
}

CREATE_SYSTEM = """You are EZO's visual designer. EZO renders the files; you only describe them.
Reply with ONLY one JSON object (no prose, no code fences): {{"items": [item, ...]}} with exactly {count} item(s).
Each item: {schema}
{variants}
Labels, titles and headlines are in the user's language ({language}). Never invent facts, \
prices, dates or statistics; use only what the user said or the conversation shows.

{rules}"""

EDIT_SPEC_SYSTEM = """You are EZO's visual designer, EDITING an existing {kind}. Apply exactly what the user asks \
and keep everything else unchanged.
Reply with ONLY one JSON object: {{"spec": the full updated spec (same fields as the current spec), \
"picture_instruction": an English instruction if the PICTURE itself must change (e.g. "make the \
background a night sky"), otherwise "", "change_summary": one short sentence in the user's language}}.
Text changes go into the spec; never put text into the picture.

{rules}"""

EDIT_IMAGE_SYSTEM = """You turn a user's request into a precise English image-editing instruction.
Reply with ONLY one JSON object: {"instruction": str (what to change and what to keep unchanged), \
"change_summary": one short sentence in the user's language}.
Do not add text to the image unless the user explicitly asks for specific words. Do not change a \
real person's identity."""

VISUAL_INSTRUCTIONS = (
    "Role: visual designer. EZO's notes below describe what was just created (or why not). "
    "Reply briefly, in at most 6 short lines:\n"
    "- what was created (titles, kind, size) and how: a generated image (name the provider and "
    "model) or an EZO-drawn diagram/graphic; say plainly when a picture is only an abstract "
    "placeholder;\n"
    "- anything that failed or was declined, honestly;\n"
    "- 2-3 concrete follow-ups (e.g. “fonini to'q ko'k qil”, “boshqa variant”, “matnni qisqartir”).\n"
    "The images appear as cards under your message: never invent links, never paste the prompt, "
    "never claim an image exists unless the notes say it was created."
)
OFFLINE_NOTE = (
    "No AI provider is connected, so EZO cannot plan the visual. Nothing was created. Tell the "
    "user to add an API key in .env."
)
NO_PROVIDER_NOTE = (
    "No image provider is configured (it needs OPENAI_API_KEY or GEMINI_API_KEY in .env), so NO "
    "image was generated and nothing was stored. Say this plainly — never describe an image as if "
    "it existed. Offer what works now: a diagram drawn by EZO, a social graphic or logo concept "
    "with EZO-rendered text and an abstract placeholder picture, or a written prompt."
)
NO_EDITOR_NOTE = (
    "The image cannot be edited: no image provider that can edit images is configured "
    "(OPENAI_API_KEY or GEMINI_API_KEY). Nothing was changed. Say so plainly."
)
REFUSED_NOTE = (
    "The image service declined this request (its content policy). Nothing was created. Say so "
    "plainly; do not suggest rewording it to get around the policy."
)


def _variants_hint(request: VisualRequest) -> str:
    if request.count < 2:
        return ""
    return (
        f"The {request.count} items are clearly different design directions, not small variations."
    )


def _theme_for(text: str) -> str:
    lowered = text.lower()
    for name in THEMES:
        if name in lowered:
            return name
    return "ezo"


class VisualAgent(Agent):
    spec = AGENTS[Intent.VISUAL]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode=self.spec.context_mode,
            instructions=VISUAL_INSTRUCTIONS,
            steps=(
                "understand_request",
                "write_spec",
                "create_visual",
                "compose_prompt",
                "generate",
            ),
        )

    async def _ask(
        self,
        tools: ToolContext,
        gathered: Gathered,
        system: str,
        request: str,
        language: str,
        step: str,
    ) -> dict[str, Any] | None:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        messages = [ChatMessage("user", request)]
        completion = await complete(
            tools.services.router,
            "chat",
            system=system,
            messages=messages,
            max_output_tokens=3_000,
            language=language,
        )
        gathered.tool_calls.append(completion.trace(step, f"{len(completion.text)} chars"))
        data = extract_json(completion.text)
        if data is None:
            messages += [
                ChatMessage("assistant", completion.text[:8_000]),
                ChatMessage(
                    "user", "Reply with ONLY the JSON object described in the instructions."
                ),
            ]
            completion = await complete(
                tools.services.router,
                "chat",
                system=system,
                messages=messages,
                max_output_tokens=3_000,
                language=language,
            )
            gathered.tool_calls.append(
                completion.trace(f"{step}_retry", f"{len(completion.text)} chars")
            )
            data = extract_json(completion.text)
        return data

    async def _upload_target(self, tools: ToolContext) -> KnowledgeDocument | None:
        return await tools.session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.user_id == tools.user_id,
                KnowledgeDocument.mime_type.like("image/%"),
                KnowledgeDocument.storage_key.is_not(None),
                or_(
                    KnowledgeDocument.project_id.is_(None),
                    KnowledgeDocument.project_id == tools.project_scope,
                ),
            )
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(1)
        )

    async def _edit_target(self, tools: ToolContext) -> Artifact | KnowledgeDocument | None:
        """The image an edit refers to: this conversation's latest image, or a newer upload."""
        artifact = await latest_artifact(
            tools.session, tools.user_id, tools.conversation_id, ("image",)
        )
        upload = await self._upload_target(tools)
        if upload is not None and (artifact is None or upload.created_at > artifact.updated_at):
            return upload
        return artifact

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        turn = ctx.turn
        visual = tools.services.visual
        if tools.services.router.is_offline:
            gathered.notes.append(OFFLINE_NOTE)
            return gathered
        try:
            if wants_edit(turn.text):
                target = await self._edit_target(tools)
                if target is not None:
                    await self._edit(ctx, gathered, target)
                    return gathered
            request = detect_request(turn.text, visual.max_per_request)
            if request.kind not in COMPOSED_KINDS and not visual.can_generate:
                gathered.notes.append(NO_PROVIDER_NOTE)
                return gathered
            await self._create(ctx, gathered, request)
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("Visual planning failed: %s", exc)
            gathered.notes.append(
                "The AI provider failed while planning the visual. Nothing was created. Say so "
                "and suggest trying again."
            )
        return gathered

    async def _create(self, ctx: GatherContext, gathered: Gathered, request: VisualRequest) -> None:
        tools, turn = ctx.tools, ctx.turn
        system = CREATE_SYSTEM.format(
            count=request.count,
            schema=ITEM_SCHEMAS[request.kind],
            variants=_variants_hint(request),
            language=turn.language,
            rules=PROMPT_RULES if request.kind != "diagram" else "",
        )
        prompt = f"User's request: {turn.text}" + (
            f"\nEarlier in the conversation: {ctx.history_hint}" if ctx.history_hint else ""
        )
        data = await self._ask(tools, gathered, system, prompt, turn.language, "write_spec")
        items = [i for i in (data or {}).get("items", []) if isinstance(i, dict)][: request.count]
        if not items:
            gathered.notes.append(
                "The visual could not be planned (the model returned no valid design). Nothing "
                "was created. Apologise and suggest trying again."
            )
            return
        theme = _theme_for(turn.text)
        for index, item in enumerate(items, start=1):
            title = str(item.get("title") or "")[:200] or f"Image {index}"
            if request.kind in COMPOSED_KINDS:
                spec = {k: v for k, v in item.items() if k not in ("title", "alt_text")}
                spec.setdefault("theme", theme)
                if request.kind == "social":
                    spec["format"] = request.social_format
                result = await call_tool(
                    gathered,
                    tools,
                    "create_graphic",
                    {"kind": request.kind, "spec": spec, "title": title, "language": turn.language},
                )
            else:
                result = await call_tool(
                    gathered,
                    tools,
                    "generate_image",
                    {
                        "prompt": prompt
                        if len(prompt := str(item.get("prompt") or "").strip()) >= 3
                        else turn.text[:4_000],
                        "title": title,
                        "kind": request.kind,
                        "aspect_ratio": request.aspect_ratio,
                        "alt_text": str(item.get("alt_text") or "")[:500],
                    },
                )
            self._report(gathered, result, title)
            if result.data and result.data.get("error_kind") == "refused":
                break  # the same request would be declined again

    async def _edit(
        self, ctx: GatherContext, gathered: Gathered, target: Artifact | KnowledgeDocument
    ) -> None:
        tools, turn = ctx.tools, ctx.turn
        kind = (target.meta or {}).get("kind") if isinstance(target, Artifact) else "image"
        if isinstance(target, Artifact) and kind in COMPOSED_KINDS:
            version = await tools.services.artifacts.current_version(tools.session, target)
            try:
                _, raw = await tools.services.artifacts.read_export(version, "spec")  # type: ignore[arg-type]
                current = json.loads(raw)
            except (ArtifactError, ValueError):
                current = None
            if isinstance(current, dict):
                current.pop("kind", None)
                system = EDIT_SPEC_SYSTEM.format(kind=kind, rules=PROMPT_RULES)
                request = (
                    f"Current spec JSON:\n{json.dumps(current, ensure_ascii=False)}\n\n"
                    f"User's request ({turn.language}): {turn.text}"
                )
                data = await self._ask(tools, gathered, system, request, turn.language, "edit_spec")
                spec = (data or {}).get("spec")
                if not isinstance(spec, dict):
                    gathered.notes.append(
                        "The change could not be planned (no valid design returned). Nothing "
                        "was changed. Apologise and suggest trying again."
                    )
                    return
                result = await call_tool(
                    gathered,
                    tools,
                    "create_graphic",
                    {
                        "kind": kind,
                        "spec": {**current, **spec},
                        "title": target.title,
                        "language": turn.language,
                        "artifact_id": str(target.id),
                        "picture_instruction": str((data or {}).get("picture_instruction") or "")[
                            :2_000
                        ],
                        "change_summary": str((data or {}).get("change_summary") or "")[:500],
                    },
                )
                self._report(gathered, result, target.title, edited=True)
                return
        if not tools.services.visual.can_edit:
            gathered.notes.append(NO_EDITOR_NOTE)
            return
        data = await self._ask(
            tools,
            gathered,
            EDIT_IMAGE_SYSTEM,
            f"User's request ({turn.language}): {turn.text}",
            turn.language,
            "write_edit_instruction",
        )
        instruction = str((data or {}).get("instruction") or "").strip() or turn.text
        args: dict[str, Any] = {
            "instruction": instruction[:4_000],
            "change_summary": str((data or {}).get("change_summary") or "")[:500],
        }
        key = "artifact_id" if isinstance(target, Artifact) else "document_id"
        args[key] = str(target.id)
        result = await call_tool(gathered, tools, "edit_image", args)
        self._report(gathered, result, target.title, edited=True)

    @staticmethod
    def _report(gathered: Gathered, result: Any, title: str, *, edited: bool = False) -> None:
        if not result.ok:
            kind = (result.data or {}).get("error_kind")
            if kind == "refused":
                gathered.notes.append(REFUSED_NOTE)
            elif kind == "unavailable":
                gathered.notes.append(NO_PROVIDER_NOTE)
            else:
                gathered.notes.append(
                    f"Creating “{title}” failed ({result.error}). Nothing was stored for it. "
                    "Say so plainly."
                )
            return
        info = result.data
        gathered.artifacts.append(info["artifact"])
        artifact = info["artifact"]
        how = (
            "drawn by EZO's layout engine (exact text)"
            if info.get("kind") == "diagram"
            else f"generated with {info.get('provider')}/{info.get('model')}"
            if info.get("provider") and not info.get("placeholder")
            else "laid out by EZO"
        )
        line = (
            ("Edited" if edited else "Created")
            + f" “{artifact['title']}” (version {artifact['version']}, "
            f"{info.get('width')}×{info.get('height')} px): {how}."
        )
        if info.get("placeholder"):
            line += (
                " Its picture is an ABSTRACT PLACEHOLDER, not a generated image"
                f" ({info.get('placeholder_reason') or 'no image'}); the text is real."
            )
        elif info.get("kind") in ("social", "logo"):
            line += " All words were rendered by EZO, not by the image model."
        if info.get("text_fits") is False:
            line += " Some text did not fit at the smallest size; suggest shortening it."
        gathered.notes.append(line)
