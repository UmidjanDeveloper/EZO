"""GeneralAgent: EZO's companion for natural conversation.

It also covers for specialized agents that are not available yet, using the
limitation notes from the catalog so it never pretends to have their tools.
"""

from __future__ import annotations

import re

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered, run_tool
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.personality.profile import ContextMode

# Signals that a general request needs deeper reasoning than quick chat.
_DEEP = re.compile(
    r"\b(tahlil|batafsil|chuqur|isbotla|strategiya|reja tuz|analy[sz]e|in detail|step by step|"
    r"pros and cons|trade.?offs?|strategy|plan for|подробно|проанализируй|стратеги|по шагам)"
)
_PROFESSIONAL = re.compile(
    r"\b(meeting|majlis|uchrashuv|hisobot|report|rasmiy|official|klient|client|mijoz|"
    r"совещани|отчёт|отчет|официальн|клиент)"
)

GENERAL_INSTRUCTIONS = (
    "Role: general companion. Help with conversation, ideas, goals, planning and everyday "
    "questions. When the user discusses goals, help make them concrete. Offer motivation "
    "only when it is genuinely appropriate."
)


class GeneralAgent(Agent):
    spec = AGENTS[Intent.GENERAL]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        text = normalize(turn.text)
        requested = turn.requested
        covering = requested.key != self.spec.key

        if covering:
            route = requested.route
            mode: ContextMode = requested.context_mode
            instructions = (
                f"{GENERAL_INSTRUCTIONS}\n\nThe user's request is best served by EZO's "
                f"{requested.names['en']}. {requested.limitation_note}"
            )
            steps = (
                "classify_intent",
                "select_agent:fallback_to_general",
                "compose_prompt",
                "generate",
                "verify",
                "save_memory",
            )
        else:
            deep = bool(_DEEP.search(text)) or len(turn.text) > 1_500
            route = "reasoning" if deep else self.spec.route
            mode = "professional" if _PROFESSIONAL.search(text) else self.spec.context_mode
            instructions = GENERAL_INSTRUCTIONS
            steps = (
                "classify_intent",
                "select_agent",
                "compose_prompt",
                "generate",
                "verify",
                "save_memory",
            )

        return AgentPlan(route=route, context_mode=mode, instructions=instructions, steps=steps)

    async def gather(self, ctx: GatherContext) -> Gathered:
        """Look into the user's files when they may be relevant (no extra tools otherwise)."""
        gathered = Gathered()
        tools = ctx.tools
        if tools.library_scope is not None:
            gathered.sources = await run_tool(
                gathered,
                tools,
                "knowledge_search",
                {
                    "query": ctx.turn.text[:500],
                    "limit": 5,
                    "strict": False,
                    "library_id": str(tools.library_scope),
                },
            )
            if not gathered.sources:
                gathered.notes.append(
                    "The selected knowledge library does not contain relevant information for "
                    "this query. Inform the user clearly that no relevant information was found."
                )
            return gathered

        if not await has_searchable_documents(tools.session, tools.user_id, tools.project_scope):
            return gathered
        about_documents = ctx.turn.requested.key == "document"
        gathered.sources = await run_tool(
            gathered,
            tools,
            "knowledge_search",
            {"query": ctx.turn.text[:500], "limit": 5, "strict": not about_documents},
        )
        return gathered
