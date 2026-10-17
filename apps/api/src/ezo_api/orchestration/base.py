"""The orchestration interface. EZO code depends on this, never on a specific engine."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ezo_api.orchestration.models import AgentOutput, Mission, MissionPlan, MissionResult, StepSpec


class MissionError(Exception):
    """A mission request cannot be fulfilled. `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class StepContext:
    """What one agent receives: the goal, its own step and its dependencies' outputs only.

    Agents never get the whole conversation; EZO adds project context, relevant
    memories and retrieved knowledge through its normal agent pipeline.
    """

    mission_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    goal: str
    step: StepSpec
    inputs: dict[str, AgentOutput] = field(default_factory=dict)


StepExecutor = Callable[[StepContext], Awaitable[AgentOutput | dict[str, Any]]]
"""Runs one step with an EZO agent (its providers, tools and policies) and returns its output."""


class OrchestrationProvider(ABC):
    name: str

    @abstractmethod
    async def plan_mission(self, goal: str) -> MissionPlan:
        """Break a goal into a small graph of specialist steps."""

    @abstractmethod
    async def start_mission(
        self, user_id: uuid.UUID, plan: MissionPlan, project_id: uuid.UUID | None = None
    ) -> Mission: ...

    @abstractmethod
    async def get_status(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission: ...

    @abstractmethod
    async def pause(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission: ...

    @abstractmethod
    async def resume(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission: ...

    @abstractmethod
    async def cancel(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission: ...

    @abstractmethod
    async def submit_approval(
        self,
        user_id: uuid.UUID,
        mission_id: uuid.UUID,
        approval_id: uuid.UUID,
        approved: bool,
        note: str = "",
    ) -> Mission: ...

    @abstractmethod
    async def list_agent_runs(
        self, user_id: uuid.UUID, mission_id: uuid.UUID
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_result(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> MissionResult: ...
