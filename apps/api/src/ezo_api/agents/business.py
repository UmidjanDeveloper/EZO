# ruff: noqa: E501
"""BusinessAgent: idea evaluation, market and competitor research, pricing, unit economics,
SWOT, pitch — every number labelled as a sourced fact, an estimate or an assumption.

- The owner's own numbers ("narxi 25 000, tannarxi 12 000, oyiga 300 ta, ijara 2 mln") are
  read by the model into JSON and the unit economics are computed by EZO.
- Market facts come only from web search results with citations; without web search EZO
  says that live market data is unavailable and invents no statistics.
- "Biznes reja tuz" also returns a Word document.
"""

from __future__ import annotations

import logging
import re
from typing import Any

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
from ezo_api.agents.llm import complete, extract_json
from ezo_api.business.economics import Inputs, compute
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage

logger = logging.getLogger(__name__)

PLAN_DOC = re.compile(r"(biznes[\s-]?reja|business plan|бизнес[\s-]?план|reja tuz|word|hujjat)")

INSTRUCTIONS = """Role: EZO's business analyst (idea, market, competitors, pricing, unit economics, SWOT, pitch).
- Label EVERY number: «[Fakt: n]» for a number from a cited web source [n], «[Hisob]» for EZO's computed unit economics (use them exactly), «[Taxmin]» for your estimate, «[Faraz]» for an assumption the owner should check.
- Never invent market statistics, competitors' figures or prices. If live sources are missing, say that market numbers need checking.
- Structure: short verdict; market & competitors (sourced); customers; pricing; unit economics; SWOT; risks; next 3 steps.
- Answer in the user's language, practical and concise."""

EXTRACT = """From the user's message, take ONLY the numbers they state for their own business. Reply with one JSON object:
{"price": number|null, "variable_cost": number|null, "fixed_costs_month": number|null, "units_per_month": number|null, "startup_cost": number|null, "currency": "so'm"|"USD"|...,
 "search_queries": [up to 2 short web search queries for the market/competitors, in the user's language]}
"mln" = 1 000 000, "ming" = 1 000. Unknown → null. Never estimate here."""


class BusinessAgent(Agent):
    spec = AGENTS[Intent.BUSINESS]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route=self.spec.route,
            context_mode=self.spec.context_mode,
            instructions=INSTRUCTIONS,
            steps=("read_numbers", "unit_economics", "web_search", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        if tools.services.router.is_offline:
            gathered.notes.append("No AI provider is connected. Say so briefly.")
            return gathered
        data: dict[str, Any] = {}
        try:
            completion = await complete(
                tools.services.router, "chat", system=EXTRACT,
                messages=[ChatMessage("user", ctx.turn.text[:6000])], max_output_tokens=600,
                language=ctx.turn.language,
            )  # fmt: skip
            data = extract_json(completion.text) or {}
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("business extraction failed: %s", exc)
        facts = compute(Inputs.from_json(data))
        if facts:
            gathered.tool_calls.append(
                {
                    "tool": "unit_economics",
                    "ok": True,
                    "summary": f"{len(facts)} facts",
                    "error": None,
                }
            )
            gathered.notes.append(
                "Unit economics computed by EZO from the owner's numbers [Hisob]:\n- "
                + "\n- ".join(facts)
            )
        else:
            gathered.notes.append(
                "The owner gave too few numbers for unit economics (price, variable cost, fixed monthly costs, volume). Ask for them at the end."
            )
        web: list[SourceRef] = []
        queries = [str(q)[:200] for q in (data.get("search_queries") or []) if str(q).strip()][:2]
        if tools.services.web_search is None:
            gathered.notes.append(
                "Live web search is not connected: no market statistics are available. Say market numbers must be checked; do not invent any."
            )
        else:
            for query in queries or [normalize(ctx.turn.text)[:200]]:
                web += await run_tool(
                    gathered, tools, "web_search", {"query": query, "max_results": 5}
                )
            if not web:
                gathered.notes.append(
                    "Web search found nothing usable; do not present market numbers as facts."
                )
        gathered.sources = [s for s in web if s.excerpt.strip()][:8]
        if PLAN_DOC.search(normalize(ctx.turn.text)):
            await self._plan_document(ctx, gathered, facts)
        return gathered

    async def _plan_document(
        self, ctx: GatherContext, gathered: Gathered, facts: list[str]
    ) -> None:
        tools = ctx.tools
        sources = "\n".join(
            f"[{i}] {s.title}: {s.excerpt[:600]}" for i, s in enumerate(gathered.sources, 1)
        )
        try:
            completion = await complete(
                tools.services.router, self.spec.route,
                system=INSTRUCTIONS + "\nWrite the full business plan in Markdown (headings, bullet lists, one table for unit economics). Cite sources as [n].",
                messages=[ChatMessage("user", f"{ctx.turn.text}\n\nEZO's computed unit economics:\n" + "\n".join(facts) + f"\n\nSources:\n{sources or 'none'}")],
                max_output_tokens=6000, language=ctx.turn.language,
            )  # fmt: skip
        except (AllProvidersFailedError, StreamInterruptedError):
            gathered.notes.append(
                "The business plan document could not be written (AI provider failed). Say so."
            )
            return
        result = await call_tool(
            gathered, tools, "create_document",
            {"title": "Biznes reja", "markdown": completion.text, "format": "docx",
             "metadata": {"action": "business_plan", "labels": "Fakt/Hisob/Taxmin/Faraz"}},
        )  # fmt: skip
        if result.ok:
            gathered.artifacts.append(result.data["artifact"])
            gathered.notes.append(
                "EZO also wrote the full business plan as a Word file; mention it."
            )
