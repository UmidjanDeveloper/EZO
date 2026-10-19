"""Tool interface.

A tool declares a Pydantic argument model, a description, and whether it is
dangerous. Tools only run through ToolRegistry.execute, which validates
arguments, enforces permissions and timeouts, and records a ToolCall row.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ezo_api.services import Services


@dataclass(slots=True)
class ToolContext:
    session: AsyncSession
    services: Services
    user_id: uuid.UUID
    run_id: uuid.UUID | None = None
    project_scope: uuid.UUID | None = None
    library_scope: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    """Conversation of the turn (artifacts created by tools are linked to it)."""
    allow_dangerous: bool = False
    """Only set after an explicit user confirmation (approval-gated tools, ROADMAP Phase 9)."""
    on_activity: Callable[[str], None] | None = None
    """Told what EZO is visibly doing (e.g. "searching") when a tool starts."""


@dataclass(slots=True)
class ToolResult:
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None
    sources: list[Any] = field(default_factory=list)


class Tool[ArgsT: BaseModel](ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    dangerous: ClassVar[bool] = False
    timeout_seconds: ClassVar[float] = 30.0
    activity: ClassVar[str] = "working"
    """Visible state while the tool runs: searching, reading, coding, creating, working."""

    @abstractmethod
    async def run(self, args: ArgsT, ctx: ToolContext) -> ToolResult: ...

    def schema(self) -> dict[str, Any]:
        """JSON schema (for model-driven tool calling)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_model.model_json_schema(),
        }
