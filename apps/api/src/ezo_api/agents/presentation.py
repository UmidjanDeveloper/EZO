# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""PresentationAgent: from a request to a real, checked PPTX.

Workflow (every step is traced; tools are logged):

    goal + audience + slide count (from the request)
    → sources: the user's files (knowledge_search / the referenced file) and,
      when the topic needs current facts, the web
    → narrative + slide architecture as a DeckSpec (one model call, "reasoning" route)
    → layout QA (overflow, tiny text, bounds, chart data…) → one repair call if needed
    → create_presentation: PPTX + PDF + web version + previews, StoryProject, artifact

A follow-up such as "make slide 3 shorter" edits the conversation's latest deck and
saves it as a NEW version of the same artifact. The final chat reply (cheap "chat"
route) only reports what was built — honestly, including remaining QA issues.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ezo_api.agents.base import (
    Agent,
    AgentPlan,
    AgentTurn,
    GatherContext,
    Gathered,
    call_tool,
    run_tool,
)
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.llm import Completion, complete, extract_json, sources_block
from ezo_api.agents.references import (
    document_source,
    find_documents,
    latest_artifact,
    refers_to_a_file,
)
from ezo_api.artifacts.service import ArtifactError
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.documents.render.build import check_deck
from ezo_api.documents.render.qa import QAReport
from ezo_api.documents.render.spec import DeckSpec, SlideSpec
from ezo_api.documents.render.theme import THEMES
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.knowledge.retrieval.sources import SourceRef, number_sources
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.base import ToolContext
from ezo_api.visual.kinds import wants_no_images

logger = logging.getLogger(__name__)

DEFAULT_SLIDES = "8-12"
MAX_SLIDES = 40
DOCUMENT_CHARS = 30_000
MAX_SOURCES = 8
_COUNT = re.compile(r"\b(\d{1,2})\s*(?:ta\s*)?-?\s*(?:slayd|slide|слайд)")
_EDIT = re.compile(
    r"\b(o'zgartir|tahrirla|qisqartir|qo'sh|olib tashla|almashtir|yaxshila|yangila|"
    r"slayd\w*\s*\d|\d+\s*-?\s*slayd|change|edit|shorten|add|remove|replace|improve|update|"
    r"slide\s*\d|измени|сократи|добавь|удали|замени|улучши|слайд\s*\d)"
)
_NEW = re.compile(r"\b(yangi taqdimot|boshqa taqdimot|new (presentation|deck)|новую презентац)")
_RESEARCH = re.compile(
    r"\b(so'nggi|oxirgi|hozirgi|bugungi|statistik|tadqiq|ma'lumotlar asosida|latest|current|"
    r"recent|statistics|market size|research|data on|последн|актуальн|статистик|исследован)"
)
_FOUR_THREE = re.compile(r"\b4\s*[:x×]\s*3\b")
SOURCES_TITLE = {"uz": "Manbalar", "en": "Sources", "ru": "Источники"}

LAYOUT_GUIDE = """Layouts and the fields each one uses:
- cover: title, subtitle, kicker (short label), body (date/presenter, one line)
- title_subtitle: title, subtitle
- section: kicker (e.g. "01"), title, subtitle — a chapter divider
- bullets: title, bullets (3-5 short points, max 6)
- hero_image: title, body (one sentence), image_prompt (English description of a picture for this slide — subject, setting, style; never text or letters in it; EZO generates it when an image provider exists, otherwise draws an abstract visual)
- big_number: title, metric {value, label}, body
- kpi: title, metrics [{value, label}] (2-4)
- quote: quote, author
- two_column / three_column: title, columns [{title, bullets}]
- comparison / before_after / problem_solution: title, columns (exactly 2) [{title, bullets}]
- timeline / process / roadmap: title, steps [{label, text}] (3-6)
- architecture: title, nodes [{id, label}] (3-8), edges [[from_id, to_id]]
- chart: title, chart {type: column|bar|line|pie|doughnut, categories [...], series [{name, values [numbers]}], unit, source}, optional bullets (max 3)
- table: title, table {headers [...] (max 7), rows [[...]] (max 12)}
- market: title, metrics [{value, label}] (e.g. TAM / SAM / SOM)
- product: title, bullets or columns
- team: title, columns [{title: person name, bullets: [role, focus]}]
- financial: title, chart or table, metrics (max 2)
- closing: title, subtitle, bullets (contacts / next steps, max 3)"""

DECK_SYSTEM = f"""You are EZO's presentation designer. You plan the narrative and the slides; EZO's own \
layout engine draws them, so you never describe positions, fonts or colours.

Reply with ONLY one JSON object (no prose, no code fences):
{{"title": str, "subtitle": str, "language": "uz"|"en"|"ru", "theme": one of {sorted(THEMES)}, \
"aspect_ratio": "16:9"|"4:3", "audience": str, "goal": str, "slides": [slide, ...]}}
Each slide: {{"layout": str, "title": str, ...layout fields..., "speaker_notes": str, \
"sources": [source numbers used on this slide]}}

{LAYOUT_GUIDE}

Rules:
- Start with "cover", end with "closing". Build a clear story: context → problem/insight → \
evidence → solution/plan → next steps. Vary layouts; avoid many plain bullet slides in a row.
- One idea per slide. Titles are short statements (max ~8 words). Bullets max ~12 words. \
No slide over 60 words of visible text; put detail in speaker_notes (2-4 sentences).
- Every slide title must be unique.
- Use hero_image where a picture really helps the story (at most 3 per deck). Image prompts must \
not depict real, identifiable private persons or imitate existing brands.
- Facts: use ONLY the numbered sources and well-established general knowledge. Never invent \
statistics, quotes, names, dates or prices. Put the source numbers a slide relies on in its \
"sources". A chart or number from a source must keep its exact values. If you show an \
illustrative or estimated number, say so on the slide (e.g. "taxminiy" / "estimate").
- If no sources support a data slide, prefer a qualitative layout over inventing numbers.
- Theme: civic for government/official, pitch for investors/startups, midnight for tech/AI, \
paper for education/reports, ezo otherwise.
- Write all slide text in the requested language."""

EDIT_SYSTEM = (
    DECK_SYSTEM
    + """

You are EDITING an existing deck. Apply exactly what the user asks and keep everything else \
unchanged (same order, text and data). Return the FULL updated deck JSON with one extra \
top-level field "change_summary": one short sentence (in the user's language) describing what \
changed."""
)

REPAIR_PROMPT = (
    "EZO's layout check found problems in your deck:\n{issues}\n\nFix them by shortening text, "
    "splitting overloaded slides, or choosing a better layout. Keep facts and source numbers "
    "unchanged. Reply with ONLY the full corrected deck JSON."
)
INVALID_PROMPT = (
    "Your reply was not a valid deck ({error}). Reply with ONLY the deck JSON object described "
    "in the instructions."
)

PRESENTATION_INSTRUCTIONS = (
    "Role: presentation designer. EZO's notes below describe the presentation that was just "
    "built (or why it could not be built). Reply briefly, in at most 8 short lines:\n"
    "- what was created: title, number of slides, the storyline in one line, the theme;\n"
    "- the quality check: say honestly if any issues remain and which slides;\n"
    "- which sources were used (cite them with [n]) — or that it is based on general knowledge;\n"
    "- the slide images: generated (name the provider) or abstract placeholders — only if the "
    "notes mention images, and never call a placeholder a real image;\n"
    "- 2-3 concrete follow-ups the user can ask for (e.g. “3-slaydni qisqartir”).\n"
    "The file appears as a card under your message (PPTX, PDF and a web version): never invent "
    "links or paths. Do not paste the slides. If the build failed, explain it plainly and "
    "suggest what to do."
)
OFFLINE_NOTE = (
    "No AI provider is connected, so EZO cannot write the presentation content. Nothing was "
    "created. Tell the user to add an API key in .env to enable presentations."
)


def requested_slides(text: str) -> int | None:
    match = _COUNT.search(normalize(text))
    if not match:
        return None
    return max(3, min(int(match.group(1)), MAX_SLIDES))


def wants_edit(text: str) -> bool:
    norm = normalize(text)
    return bool(_EDIT.search(norm)) and not _NEW.search(norm)


def issues_text(report: QAReport) -> str:
    return "\n".join(f"- slide {i.slide}: {i.message}" for i in report.errors[:20])


def parse_deck(data: dict[str, Any] | None, language: str) -> tuple[DeckSpec | None, str]:
    if data is None:
        return None, "no JSON object found"
    data = {**data, "language": language}
    try:
        return DeckSpec.model_validate(data), ""
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        return None, f"{where}: {first.get('msg', 'invalid')}"


def add_sources_slide(deck: DeckSpec, sources: list[SourceRef]) -> list[SourceRef]:
    """Append a sources slide (before the closing slide). Returns the sources it lists."""
    cited = sorted({n for slide in deck.slides for n in slide.sources})
    by_number = {s.n: s for s in sources}
    used = [by_number[n] for n in cited if n in by_number] or list(sources)
    if not used:
        return []
    bullets = []
    for source in used:
        where = source.url or source.source_name
        bullets.append(f"[{source.n}] {source.title} — {where}"[:220])
    slide = SlideSpec(
        layout="bullets",
        title=SOURCES_TITLE.get(deck.language, "Sources"),
        bullets=bullets,
        sources=[s.n for s in used],
    )
    position = len(deck.slides)
    if deck.slides and deck.slides[-1].layout == "closing":
        position -= 1
    if len(deck.slides) < 60:
        deck.slides.insert(position, slide)
    return used


@dataclass(slots=True)
class ImageStats:
    planned: int = 0
    generated: int = 0
    reused: int = 0
    refused: int = 0
    limited: int = 0
    failed: str | None = None
    no_provider: bool = False
    skipped: bool = False
    provider: str = ""

    def notes(self, missing: int = 0) -> list[str]:
        if not self.planned:
            return []
        lines = []
        if self.generated:
            lines.append(
                f"{self.generated} slide image(s) were generated with {self.provider} and "
                "placed on the slides; each is also saved as an image artifact."
            )
        if self.reused:
            lines.append(f"{self.reused} existing slide image(s) were kept.")
        if self.no_provider:
            lines.append(
                "Some slides planned an image, but no image provider is configured, so an "
                "abstract visual (not a real image) is used there."
            )
        if self.skipped:
            lines.append("Slide images were skipped as requested; abstract visuals are used.")
        if self.limited:
            lines.append(
                f"{self.limited} more slide(s) use an abstract visual because of the per-deck "
                "image limit (EZO_IMAGE_MAX_PER_DECK)."
            )
        if self.refused:
            lines.append(f"The image service declined {self.refused} slide image(s).")
        if self.failed:
            lines.append(
                f"Image generation failed ({self.failed}); remaining slides use abstract visuals."
            )
        if missing:
            lines.append(f"{missing} earlier slide image(s) could not be loaded.")
        return lines


class PresentationAgent(Agent):
    spec = AGENTS[Intent.PRESENTATION]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",  # the deck itself is written on the reasoning route during gather
            context_mode=self.spec.context_mode,
            instructions=PRESENTATION_INSTRUCTIONS,
            steps=(
                "understand_goal",
                "gather_sources",
                "plan_deck",
                "layout_qa",
                "export_pptx",
                "story_project",
                "compose_prompt",
                "generate",
            ),
        )

    async def _sources(self, ctx: GatherContext, gathered: Gathered) -> list[SourceRef]:
        tools = ctx.tools
        text = ctx.turn.text
        sources: list[SourceRef] = []
        if await has_searchable_documents(tools.session, tools.user_id, tools.project_scope):
            for ref in await find_documents(
                tools.session, tools.user_id, tools.project_scope, text
            ):
                read = await call_tool(
                    gathered,
                    tools,
                    "read_document",
                    {"document_id": str(ref.document.id), "max_chars": DOCUMENT_CHARS},
                )
                if read.ok:
                    body = str(read.data.get("text", ""))
                    sources.append(document_source(ref.document, body, DOCUMENT_CHARS))
            if not sources:
                sources += await run_tool(
                    gathered,
                    tools,
                    "knowledge_search",
                    {"query": text[:500], "limit": 5, "strict": not refers_to_a_file(text)},
                )
        if tools.services.web_search is not None and _RESEARCH.search(normalize(text)):
            web = await run_tool(
                gathered, tools, "web_search", {"query": text[:300], "max_results": 5}
            )
            for source in web[:2]:
                if source.url:
                    pages = await run_tool(gathered, tools, "web_fetch", {"url": source.url})
                    if pages and len(pages[0].excerpt) > len(source.excerpt):
                        source.excerpt = pages[0].excerpt
            sources += [s for s in web if s.excerpt.strip()][:4]
        elif _RESEARCH.search(normalize(text)):
            gathered.notes.append(
                "Web search is not configured, so no current data was looked up; the deck "
                "avoids specific recent statistics."
            )
        return number_sources(sources[:MAX_SOURCES])

    async def _existing_deck(
        self, tools: ToolContext, text: str
    ) -> tuple[Any, dict[str, Any]] | None:
        if not wants_edit(text):
            return None
        artifact = await latest_artifact(
            tools.session, tools.user_id, tools.conversation_id, ("presentation",)
        )
        if artifact is None:
            return None
        version = await tools.services.artifacts.current_version(tools.session, artifact)
        if version is None:
            return None
        try:
            _, raw = await tools.services.artifacts.read_export(version, "spec")
            spec = json.loads(raw)
        except (ArtifactError, ValueError):
            return None
        return artifact, spec

    async def _ask(
        self,
        tools: ToolContext,
        gathered: Gathered,
        route: str,
        system: str,
        messages: list[ChatMessage],
        slides: int,
        language: str,
        step: str,
    ) -> Completion:
        if tools.on_activity is not None:
            tools.on_activity("creating")
        completion = await complete(
            tools.services.router,
            route,
            system=system,
            messages=messages,
            max_output_tokens=min(32_000, 2_000 + 700 * slides),
            language=language,
        )
        gathered.tool_calls.append(completion.trace(step, f"{len(completion.text)} chars"))
        return completion

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        turn = ctx.turn
        if tools.services.router.is_offline:
            gathered.notes.append(OFFLINE_NOTE)
            return gathered

        existing = await self._existing_deck(tools, turn.text)
        # An edit keeps the deck's own sources (and its sources slide) unchanged.
        sources = [] if existing is not None else await self._sources(ctx, gathered)
        count = requested_slides(turn.text)
        slides_hint = str(count) if count else DEFAULT_SLIDES
        aspect = "4:3" if _FOUR_THREE.search(turn.text) else "16:9"

        if existing is not None:
            system = EDIT_SYSTEM
            request = (
                f"Current deck JSON:\n{json.dumps(existing[1], ensure_ascii=False)}\n\n"
                f"{sources_block(sources)}\n\nUser's request ({turn.language}): {turn.text}"
            )
            slide_budget = max(len(existing[1].get("slides", [])), count or 0) + 3
        else:
            system = DECK_SYSTEM
            request = (
                f"User's request: {turn.text}\n"
                + (f"Earlier in the conversation: {ctx.history_hint}\n" if ctx.history_hint else "")
                + f"Language: {turn.language}. Slides: {slides_hint} (including cover and "
                f"closing). Aspect ratio: {aspect}.\n\n{sources_block(sources)}"
            )
            slide_budget = count or 12

        messages = [ChatMessage("user", request)]
        try:
            completion = await self._ask(
                tools,
                gathered,
                "reasoning",
                system,
                messages,
                slide_budget,
                turn.language,
                "plan_deck",
            )
            data = extract_json(completion.text)
            deck, error = parse_deck(data, turn.language)
            if deck is None:
                messages += [
                    ChatMessage("assistant", completion.text[:20_000]),
                    ChatMessage("user", INVALID_PROMPT.format(error=error)),
                ]
                completion = await self._ask(
                    tools,
                    gathered,
                    "reasoning",
                    system,
                    messages,
                    slide_budget,
                    turn.language,
                    "repair_deck_json",
                )
                data = extract_json(completion.text)
                deck, error = parse_deck(data, turn.language)
            if deck is None:
                gathered.notes.append(
                    f"The presentation could not be built: the model did not return a valid "
                    f"slide plan ({error}). Nothing was created. Apologise and suggest trying "
                    f"again, perhaps with fewer slides."
                )
                gathered.sources = sources
                return gathered

            report = check_deck(deck)
            if report.errors:
                gathered.tool_calls.append(
                    {
                        "tool": "layout_qa",
                        "ok": False,
                        "summary": f"{len(report.errors)} errors",
                        "error": None,
                    }
                )
                messages += [
                    ChatMessage("assistant", completion.text[:20_000]),
                    ChatMessage("user", REPAIR_PROMPT.format(issues=issues_text(report))),
                ]
                repaired = await self._ask(
                    tools,
                    gathered,
                    "reasoning",
                    system,
                    messages,
                    slide_budget,
                    turn.language,
                    "repair_layout",
                )
                fixed, _ = parse_deck(extract_json(repaired.text), turn.language)
                if fixed is not None and len(check_deck(fixed).errors) < len(report.errors):
                    deck, completion = fixed, repaired
                    data = extract_json(repaired.text)
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("Deck generation failed: %s", exc)
            gathered.notes.append(
                "The presentation could not be built because the AI provider failed while "
                "writing it. Nothing was created. Say so and suggest trying again."
            )
            gathered.sources = sources
            return gathered

        if aspect == "4:3" and existing is None:
            deck.aspect_ratio = "4:3"
        images = await self._visuals(
            tools, gathered, deck, existing[1] if existing else None, turn.text
        )
        used = add_sources_slide(deck, sources) if sources else []
        references = [s.to_metadata() for s in used]
        if existing is not None:
            references = list(existing[0].source_references or [])
        change_summary = str((data or {}).get("change_summary", ""))[:500]
        result = await call_tool(
            gathered,
            tools,
            "create_presentation",
            {
                "deck": deck.model_dump(mode="json"),
                "artifact_id": str(existing[0].id) if existing else None,
                "change_summary": change_summary or ("Edited" if existing else ""),
                "source_references": references,
                "provider": completion.provider,
                "model": completion.model,
            },
        )
        for source in sources:  # the short report after the build does not need whole files
            source.excerpt = source.excerpt[:1_200]
        gathered.sources = sources
        if not result.ok:
            gathered.notes.append(
                f"Building the presentation file failed ({result.error}). Nothing was saved. "
                "Explain this plainly."
            )
            return gathered
        info = result.data
        gathered.artifacts.append(info["artifact"])
        gathered.notes.append(
            self._summary_note(deck, info, existing is not None, change_summary, images)
        )
        return gathered

    async def _visuals(
        self,
        tools: ToolContext,
        gathered: Gathered,
        deck: DeckSpec,
        previous: dict[str, Any] | None,
        text: str,
    ) -> ImageStats:
        """Give hero slides a generated image (VisualAgent's generate_image tool).

        An edited deck keeps its images: a slide with the same image prompt (or title) as
        before reuses that image artifact. Image ids written by the model are ignored.
        """
        stats = ImageStats()
        by_prompt: dict[str, str] = {}
        by_title: dict[str, str] = {}
        for old in (previous or {}).get("slides", []):
            if isinstance(old, dict) and old.get("image_artifact_id"):
                by_prompt.setdefault(str(old.get("image_prompt") or ""), old["image_artifact_id"])
                by_title.setdefault(str(old.get("title") or ""), old["image_artifact_id"])
        wanted: list[SlideSpec] = []
        for slide in deck.slides:
            slide.image_artifact_id = ""
            if slide.layout != "hero_image" or not slide.image_prompt:
                continue
            stats.planned += 1
            reused = (slide.image_prompt and by_prompt.get(slide.image_prompt)) or by_title.get(
                slide.title
            )
            if reused:
                slide.image_artifact_id = reused
                stats.reused += 1
            else:
                wanted.append(slide)
        visual = tools.services.visual
        if not wanted:
            return stats
        if wants_no_images(text) or visual.max_per_deck == 0:
            stats.skipped = True
            return stats
        if not visual.can_generate:
            stats.no_provider = True
            return stats
        aspect = "2:3" if deck.aspect_ratio == "4:3" else "3:4"
        stats.limited = max(0, len(wanted) - visual.max_per_deck)
        for slide in wanted[: visual.max_per_deck]:
            result = await call_tool(
                gathered,
                tools,
                "generate_image",
                {
                    "prompt": f"{slide.image_prompt}. A presentation visual that suits a "
                    f"{deck.theme} slide theme. No text, letters or logos in the image.",
                    "title": f"{deck.title} — {slide.title}"[:200],
                    "kind": "presentation",
                    "aspect_ratio": aspect,
                    "alt_text": slide.title[:500],
                    "used_in": deck.title[:300],
                },
            )
            if result.ok:
                slide.image_artifact_id = result.data["artifact"]["id"]
                stats.generated += 1
                stats.provider = f"{result.data['provider']}/{result.data['model']}"
            elif (result.data or {}).get("error_kind") == "refused":
                stats.refused += 1
            else:
                stats.failed = result.error or "the image service failed"
                break  # an unavailable service would fail for every slide
        return stats

    @staticmethod
    def _summary_note(
        deck: DeckSpec,
        info: dict[str, Any],
        edited: bool,
        change_summary: str,
        images: ImageStats | None = None,
    ) -> str:
        qa = info["qa"]
        issues = "; ".join(
            f"slide {i['slide']}: {i['message']}"
            for i in qa["issues"]
            if i["severity"] in ("error", "warning")
        )[:1_200]
        outline = " → ".join(slide.title for slide in deck.slides[:14] if slide.title)[:900]
        lines = [
            ("Edited" if edited else "Created")
            + f" presentation “{deck.title}” (version {info['artifact']['version']}): "
            f"{info['slides']} slides, theme {info['theme']}, {deck.aspect_ratio}.",
            f"Storyline: {outline}",
            "Layout check: "
            + ("passed" if qa["passed"] else f"{qa['errors']} problem(s) remain")
            + (f"; notes: {issues}" if issues else ""),
            "Files: PPTX (editable), PDF, web version, slide previews; a story project "
            "keeps the narrative for later video use.",
        ]
        if info.get("fixes"):
            lines.append("Automatic fixes: " + "; ".join(info["fixes"])[:600])
        if change_summary:
            lines.append(f"What changed: {change_summary}")
        if images is not None:
            lines.extend(images.notes(info.get("missing_images", 0)))
        return "\n".join(lines)
