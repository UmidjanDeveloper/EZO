"""Agent interface.

An agent decides *how* a turn is handled: which model route to use, which
instructions to add to the system prompt and which steps to run. EzoCore owns
the shared pipeline (context, memory, model call, persistence, tracing).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ezo_api.agents.catalog import AgentSpec
from ezo_api.core.intent import IntentResult
from ezo_api.personality.profile import ContextMode


@dataclass(frozen=True, slots=True)
class AgentTurn:
    """What the agent is asked to handle."""

    text: str
    language: str
    intent: IntentResult
    requested: AgentSpec
    """The agent the intent asked for (may be unavailable and covered by another)."""


@dataclass(frozen=True, slots=True)
class AgentPlan:
    route: str
    context_mode: ContextMode
    instructions: str
    steps: tuple[str, ...]


class Agent(ABC):
    spec: AgentSpec

    @abstractmethod
    def plan(self, turn: AgentTurn) -> AgentPlan:
        """Decide route, style and instructions for this turn."""
