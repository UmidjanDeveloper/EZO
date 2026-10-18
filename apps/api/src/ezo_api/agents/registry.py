"""Agent registry: maps an intent to the agent that will handle it."""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.agents.base import Agent
from ezo_api.agents.catalog import AGENTS, AgentSpec
from ezo_api.agents.document import DocumentAgent
from ezo_api.agents.general import GeneralAgent
from ezo_api.agents.language_coach import LanguageCoachAgent
from ezo_api.agents.presentation import PresentationAgent
from ezo_api.agents.research import ResearchAgent
from ezo_api.agents.visual import VisualAgent
from ezo_api.core.intent import Intent


@dataclass(frozen=True, slots=True)
class AgentSelection:
    agent: Agent
    requested: AgentSpec
    """The agent the intent asked for."""

    @property
    def is_fallback(self) -> bool:
        return self.agent.spec.key != self.requested.key


class AgentRegistry:
    def __init__(self, agents: list[Agent] | None = None) -> None:
        self._agents: dict[Intent, Agent] = {}
        self._general = GeneralAgent()
        for agent in agents or [
            self._general,
            ResearchAgent(),
            DocumentAgent(),
            PresentationAgent(),
            LanguageCoachAgent(),
            VisualAgent(),
        ]:
            self._agents[agent.spec.intent] = agent

    def select(self, intent: Intent, forced_agent: str | None = None) -> AgentSelection:
        """Pick the agent for an intent. `forced_agent` lets the user choose manually."""
        if forced_agent:
            for spec in AGENTS.values():
                if spec.key == forced_agent:
                    intent = spec.intent
                    break
        requested = AGENTS[intent]
        agent = self._agents.get(intent) if requested.available else None
        return AgentSelection(agent=agent or self._general, requested=requested)

    @staticmethod
    def catalog() -> list[AgentSpec]:
        return list(AGENTS.values())
