"""GeneralAgent: EZO's companion for natural conversation.

It also covers for specialized agents that are not available yet, using the
limitation notes from the catalog so it never pretends to have their tools.
"""

from __future__ import annotations

import re

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
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
