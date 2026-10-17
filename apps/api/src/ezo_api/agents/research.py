"""ResearchAgent: current information from the web and the user's files, with citations.

Workflow (each step is a logged tool call):

    plan search queries (fast model) → knowledge_search (user's files)
    → web_search (1-3 queries) → rank by reliability/recency → web_fetch top pages
    → answer with numbered, verified citations (EzoCore)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered, run_tool
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.providers.types import ChatMessage, ChatRequest, TextDelta
from ezo_api.tools.base import ToolContext

logger = logging.getLogger(__name__)

MAX_QUERIES = 3
MAX_WEB_SOURCES = 6
PAGES_TO_READ = 3
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_RECENT = re.compile(
    r"\b(latest|today|this week|current|news|recent|bugun|hozirgi|so'nggi|oxirgi|yangilik|"
    r"сегодня|последн|новост|актуальн)",
    re.IGNORECASE,
)

RESEARCH_INSTRUCTIONS = (
    "Role: research analyst. Build the answer from the numbered sources provided below.\n"
    "- Compare the sources; if they disagree, say so and explain which is more reliable and why.\n"
    "- Prefer primary/official sources (marked 'primary') over secondary ones.\n"
    "- For anything time-sensitive, mention the date of the information ('as of …') and warn "
    "if the newest source may be outdated.\n"
    "- Separate facts (cited) from your own assumptions or opinions (label them as such).\n"
    "- Never invent statistics, quotes, URLs, titles or dates. If the sources are not enough, "
    "say exactly what is missing.\n"
    "- Be concise and structured; lead with the answer."
)
NO_WEB_NOTE = (
    "Web search is not configured in this EZO installation, so no live web results were "
    "retrieved. Say so briefly, answer from the user's files (if any sources are given) and "
    "general knowledge, and clearly mark what may be outdated. To enable web search the owner "
    "can add TAVILY_API_KEY, or use an Anthropic key with web search enabled."
)

PLANNER_PROMPT = (
    "You plan web searches for a research assistant. Reply with ONLY a JSON object: "
    '{"queries": ["..."], "recent": true|false}. Give 1-3 short search queries that together '
    "cover the request. Use English for global topics and the user's language (or Russian) "
    "for local topics such as Uzbekistan. Set recent to true if the request needs current or "
    "latest information."
)


@dataclass(frozen=True, slots=True)
class SearchPlan:
    queries: list[str]
    recent: bool
    planned_by_model: bool


def parse_plan(raw: str, fallback_query: str) -> SearchPlan:
    recent_guess = bool(_RECENT.search(fallback_query))
    match = _JSON_OBJECT.search(raw or "")
    if match:
        try:
            data = json.loads(match.group(0))
            queries = [
                " ".join(str(q).split())[:300]
                for q in data.get("queries", [])
                if isinstance(q, str) and q.strip()
            ][:MAX_QUERIES]
            if queries:
                return SearchPlan(queries, bool(data.get("recent", recent_guess)), True)
        except (ValueError, AttributeError):
            pass
    return SearchPlan([fallback_query[:300]], recent_guess, False)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    host = (parts.hostname or "").removeprefix("www.")
    return urlunsplit((parts.scheme, host, path, parts.query, ""))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")[:25])
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def rank_web_sources(sources: list[SourceRef], recent: bool) -> list[SourceRef]:
    """Deduplicate by URL; order by primary, reliability and (for recent questions) date."""
    unique: dict[str, SourceRef] = {}
    for source in sources:
        if source.url:
            unique.setdefault(_normalize_url(source.url), source)

    def key(source: SourceRef) -> tuple[float, ...]:
        published = _parse_date(source.date)
        age_bonus = 0.0
        if recent and published is not None:
            days = max((datetime.now(UTC) - published).days, 0)
            age_bonus = max(0.0, 0.3 - days / 365)
        return (1.0 if source.primary else 0.0, source.reliability + age_bonus)

    return sorted(unique.values(), key=key, reverse=True)


class ResearchAgent(Agent):
    spec = AGENTS[Intent.RESEARCH]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route=self.spec.route,
            context_mode=self.spec.context_mode,
            instructions=RESEARCH_INSTRUCTIONS,
            steps=(
                "plan_queries",
                "knowledge_search",
                "web_search",
                "web_fetch",
                "compose_prompt",
                "generate",
                "verify_citations",
            ),
        )

    async def _plan_queries(self, tools: ToolContext, text: str, history_hint: str) -> SearchPlan:
        router = tools.services.router
        if router.is_offline:
            return parse_plan("", text)
        request_text = text if not history_hint else f"Earlier: {history_hint}\nNow: {text}"
        try:
            routed = router.open("chat")
            parts: list[str] = []
            request = ChatRequest(
                model="",
                messages=[ChatMessage("user", request_text[:2000])],
                system=PLANNER_PROMPT,
                max_output_tokens=400,
            )
            async for event in routed.stream(request):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
            return parse_plan("".join(parts), text)
        except Exception as exc:  # planning is an optimisation; never block research
            logger.warning("Query planning failed, using the question as query: %s", exc)
            return parse_plan("", text)

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        text = ctx.turn.text
        plan = await self._plan_queries(tools, text, ctx.history_hint)
        gathered.tool_calls.append(
            {
                "tool": "plan_queries",
                "ok": True,
                "summary": f"{len(plan.queries)} queries, recent={plan.recent}, "
                f"{'model' if plan.planned_by_model else 'fallback'}",
                "error": None,
            }
        )

        knowledge: list[SourceRef] = []
        if await has_searchable_documents(tools.session, tools.user_id, tools.project_scope):
            knowledge = await run_tool(
                gathered, tools, "knowledge_search", {"query": text[:500], "limit": 3}
            )

        web: list[SourceRef] = []
        if tools.services.web_search is None:
            gathered.notes.append(NO_WEB_NOTE)
        else:
            for query in plan.queries:
                web += await run_tool(
                    gathered,
                    tools,
                    "web_search",
                    {"query": query, "max_results": 5, "recent": plan.recent},
                )
            if not web:
                errors = [c["error"] for c in gathered.tool_calls if c["tool"] == "web_search"]
                gathered.notes.append(
                    "Web search returned no usable results"
                    + (f" ({errors[0]})" if errors and errors[0] else "")
                    + ". Say so and do not present unverified information as current."
                )

        web = rank_web_sources(web, plan.recent)[:MAX_WEB_SOURCES]
        for source in web[:PAGES_TO_READ]:
            if not source.url:
                continue
            pages = await run_tool(gathered, tools, "web_fetch", {"url": source.url})
            if pages:
                page = pages[0]
                if len(page.excerpt) > len(source.excerpt):
                    source.excerpt = page.excerpt
                    source.kind = "web_page"
                source.date = source.date or page.date
                source.title = source.title or page.title

        gathered.sources = knowledge + [s for s in web if s.excerpt.strip()]
        if plan.recent:
            gathered.notes.append(
                "The user wants current information: state the date of each key fact."
            )
        return gathered
