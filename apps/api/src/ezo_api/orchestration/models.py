"""Mission data: plans, steps, structured agent output, events and approvals.

These are plain in-memory types for now. The persistent tables (Mission,
MissionStep, MissionAgent, MissionEvent, MissionApproval, MissionArtifact) are
specified in docs/RUFLO_INTEGRATION_PLAN.md and arrive with mission execution
in chat; the fields here match them so the switch is mechanical.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MissionStatus = Literal[
    "created",
    "planning",
    "running",
    "waiting_for_user",
    "paused",
    "completed",
    "failed",
    "cancelled",
]
StepStatus = Literal[
    "pending",
    "waiting_for_user",
    "running",
    "completed",
    "failed",
    "rejected",
    "skipped",
    "cancelled",
]
AgentType = Literal[
    "research",
    "business",
    "document",
    "presentation",
    "visual",
    "developer",
    "legal_research",
    "qa",
]
TERMINAL_MISSION: frozenset[str] = frozenset({"completed", "failed", "cancelled"})
TERMINAL_STEP: frozenset[str] = frozenset(
    {"completed", "failed", "rejected", "skipped", "cancelled"}
)

MAX_STEPS = 12
MAX_PARALLEL_AGENTS = 6
"""Anti-drift default: a small team of specialists, never dozens of agents."""
_STEP_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


def now() -> datetime:
    return datetime.now(UTC)


class StepSpec(BaseModel):
    """One planned unit of work, owned by exactly one agent role."""

    id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    agent_type: AgentType
    depends_on: list[str] = Field(default_factory=list, max_length=MAX_STEPS)
    requires_approval: bool = False
    approval_reason: str = Field(default="", max_length=1_000)
    """What will change and why, shown to the user before the step runs."""
    max_retries: int = Field(default=1, ge=0, le=3)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _STEP_ID.match(value):
            raise ValueError("step ids are short lowercase identifiers")
        return value

    @model_validator(mode="after")
    def _approval_needs_reason(self) -> StepSpec:
        if self.requires_approval and not self.approval_reason.strip():
            raise ValueError(f"step {self.id!r} needs an approval_reason")
        return self


class MissionPlan(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4_000)
    steps: list[StepSpec] = Field(min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _valid_graph(self) -> MissionPlan:
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique")
        known = set(ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(f"step {step.id!r} depends on unknown steps {sorted(unknown)}")
            if step.id in step.depends_on:
                raise ValueError(f"step {step.id!r} depends on itself")
        # Kahn's algorithm: every step must be reachable without a cycle.
        remaining = {s.id: set(s.depends_on) for s in self.steps}
        while remaining:
            ready = [sid for sid, deps in remaining.items() if not deps]
            if not ready:
                raise ValueError(f"dependency cycle between {sorted(remaining)}")
            for sid in ready:
                del remaining[sid]
            for deps in remaining.values():
                deps.difference_update(ready)
        return self


class ArtifactLink(BaseModel):
    id: str
    title: str = ""
    type: str = ""
    version: int = 1


class AgentOutput(BaseModel):
    """The contract every mission agent returns (validated; free text alone is not accepted)."""

    status: Literal["completed", "failed", "needs_input"]
    summary: str = Field(min_length=1, max_length=4_000)
    findings: list[str] = Field(default_factory=list, max_length=50)
    artifacts: list[ArtifactLink] = Field(default_factory=list, max_length=20)
    files_changed: list[str] = Field(default_factory=list, max_length=200)
    sources: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    errors: list[str] = Field(default_factory=list, max_length=20)
    next_recommendation: str = Field(default="", max_length=1_000)


@dataclass(slots=True)
class MissionStep:
    spec: StepSpec
    index: int
    status: StepStatus = "pending"
    attempts: int = 0
    output: AgentOutput | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MissionEvent:
    """A visible timeline entry. `presence` is the orb state it maps to (real activity only)."""

    kind: str
    message: str
    step_id: str | None = None
    presence: str | None = None
    at: datetime = field(default_factory=now)


@dataclass(slots=True)
class MissionApproval:
    id: uuid.UUID
    step_id: str
    action: str
    reason: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    decided_at: datetime | None = None
    note: str = ""


@dataclass(slots=True)
class Mission:
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    plan: MissionPlan
    orchestration_provider: str
    steps: list[MissionStep]
    status: MissionStatus = "created"
    created_at: datetime = field(default_factory=now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    events: list[MissionEvent] = field(default_factory=list)
    approvals: list[MissionApproval] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.plan.title

    @property
    def progress(self) -> float:
        done = sum(1 for s in self.steps if s.status in TERMINAL_STEP)
        return round(done / len(self.steps), 3) if self.steps else 0.0

    @property
    def current_step(self) -> MissionStep | None:
        for status in ("running", "waiting_for_user"):
            for step in self.steps:
                if step.status == status:
                    return step
        return None

    def step(self, step_id: str) -> MissionStep:
        for step in self.steps:
            if step.spec.id == step_id:
                return step
        raise KeyError(step_id)

    @property
    def artifacts(self) -> list[ArtifactLink]:
        """Every artifact the mission's agents created (deduplicated, in step order)."""
        seen: dict[str, ArtifactLink] = {}
        for step in self.steps:
            for link in step.output.artifacts if step.output else []:
                seen[link.id] = link
        return list(seen.values())


@dataclass(frozen=True, slots=True)
class MissionResult:
    mission_id: uuid.UUID
    status: MissionStatus
    summary: str
    outputs: dict[str, AgentOutput]
    artifacts: list[ArtifactLink]
    skipped_steps: list[str]
    failure_reason: str | None
