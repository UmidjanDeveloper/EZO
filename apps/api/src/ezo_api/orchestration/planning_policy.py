"""Attenuating planning policy; never an execution capability.

Restriction algebra adapted from ruvnet/ruflo capability restrictions at
5d99b57e7862c0623cf26e0c152dff60e3b50346,
v3/@claude-flow/guidance/src/capabilities.ts (MIT; retained third-party notice).
Availability distinguishes missing prerequisites from tool existence, following
REA CapabilityInventory/WindowsCapabilities at c8ed32853881b08aa83459d4da55a28a4e09b0c8.
No Ruflo/REA runtime, shell, debugger or device command is invoked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PlanningPolicy:
    actor_id: uuid.UUID
    tools: frozenset[str]
    expires_at: datetime

    def restrict(self, tools: frozenset[str], expires_at: datetime) -> PlanningPolicy:
        return PlanningPolicy(self.actor_id, self.tools & tools, min(self.expires_at, expires_at))

    def allows_plan(self, actor_id: uuid.UUID, tool: str, at: datetime) -> bool:
        return actor_id == self.actor_id and tool in self.tools and at < self.expires_at


def availability(required: frozenset[str], verified: frozenset[str]) -> dict[str, object]:
    """A claimed tool name cannot stand in for a verified prerequisite."""
    missing = sorted(required - verified)
    return {
        "available": not missing,
        "missing_prerequisites": missing,
        "execution_authorized": False,
    }
