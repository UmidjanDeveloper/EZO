"""Agent interface.

An agent decides *how* a turn is handled: which model route to use, which
instructions to add to the system prompt and which steps to run. EzoCore owns
the shared pipeline (context, memory, model call, persistence, tracing).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ezo_api.agents.catalog import AgentSpec
from ezo_api.core.intent import IntentResult
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.personality.profile import ContextMode

if TYPE_CHECKING:
    from ezo_api.tools.base import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class AgentTurn:
    """What the agent is asked to handle."""

    text: str
    language: str
    intent: IntentResult
    requested: AgentSpec
    """The agent the intent asked for (may be unavailable and covered by another)."""
    channel: str = "text"
    """"voice" when the user spoke the message."""
    speech_seconds: float | None = None
    """Measured speaking time of a voice message (None when typed or not measured)."""


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

    async def gather(self, ctx: GatherContext) -> Gathered:
        """Collect sources with tools before the answer (default: nothing)."""
        return Gathered()


@dataclass(slots=True)
class GatherContext:
    """What an agent can use to collect information before EZO answers."""

    turn: AgentTurn
    tools: ToolContext
    history_hint: str = ""
    """The previous user message, to help interpret follow-up questions."""


@dataclass(slots=True)
class Gathered:
    sources: list[SourceRef] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Facts about the gathering itself (e.g. 'web search not configured') for the prompt."""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    """Artifacts created during this turn ({id, title, type, version}); shown under the answer."""


async def call_tool(
    gathered: Gathered, ctx: ToolContext, name: str, arguments: dict[str, Any]
) -> ToolResult:
    """Execute a registered tool and record a trace entry."""
    result = await ctx.services.tools.execute(name, arguments, ctx)
    gathered.tool_calls.append(
        {"tool": name, "ok": result.ok, "summary": result.summary, "error": result.error}
    )
    return result


async def run_tool(
    gathered: Gathered, ctx: ToolContext, name: str, arguments: dict[str, Any]
) -> list[SourceRef]:
    """Execute a registered tool, record a trace entry, return its sources."""
    result = await call_tool(gathered, ctx, name, arguments)
    return list(result.sources) if result.ok else []
