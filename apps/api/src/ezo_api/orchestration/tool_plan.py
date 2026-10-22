"""TaskBench-style tool graphs validated against EZO's existing DAG and registry.

EasyTool instruction cards and TaskBench node/dependency separation are adapted
from microsoft/JARVIS7624cf3. No benchmark data, agent executor, model or upstream
code is imported. This inspector cannot execute or authorize an action.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ezo_api.db.base import utcnow
from ezo_api.orchestration.models import MAX_STEPS, MissionPlan, StepSpec
from ezo_api.orchestration.planning_policy import PlanningPolicy
from ezo_api.tools.registry import ToolRegistry

INSPECTABLE_TOOLS = frozenset(
    {"calculate_percentages", "knowledge_search", "web_search", "web_fetch", "official_search"}
)


class ToolNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    tool: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: dict[str, Any] = Field(max_length=32)

    @field_validator("arguments")
    @classmethod
    def bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("Tool arguments must be bounded valid Unicode JSON.") from exc
        if len(encoded) > 4096 or b"\\u0000" in encoded:
            raise ValueError("Tool argument limit or invalid NUL.")
        return value


class ToolEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    target: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")


class ToolGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[ToolNode] = Field(min_length=1, max_length=MAX_STEPS)
    links: list[ToolEdge] = Field(default_factory=list, max_length=MAX_STEPS * MAX_STEPS)


class PlanInspectionError(ValueError):
    pass


def inspect_graph(graph: ToolGraph, registry: ToolRegistry, actor: uuid.UUID) -> dict[str, Any]:
    now = utcnow()
    policy = PlanningPolicy(actor, INSPECTABLE_TOOLS, now + timedelta(minutes=1))
    policy = policy.restrict(frozenset(registry.names()), now + timedelta(minutes=1))
    ids = {node.id for node in graph.nodes}
    pairs = {(edge.source, edge.target) for edge in graph.links}
    if len(pairs) != len(graph.links) or any(a not in ids or b not in ids for a, b in pairs):
        raise PlanInspectionError("invalid_graph_edges")
    try:
        # Reuse the shipped MissionPlan's unique IDs, missing-dependency and cycle
        # checks. A Mission is never started or passed to NativeOrchestrationProvider.
        MissionPlan(
            title="Tool graph inspection",
            goal="Validate data, without action authority",
            steps=[
                StepSpec(
                    id=node.id,
                    title=node.tool,
                    agent_type="qa",
                    depends_on=sorted(a for a, b in pairs if b == node.id),
                )
                for node in graph.nodes
            ],
        )
    except ValidationError as exc:
        raise PlanInspectionError("invalid_dependency_graph") from exc
    normalized = []
    for node in graph.nodes:
        if not policy.allows_plan(actor, node.tool, now):
            raise PlanInspectionError("unsupported_or_unavailable_tool")
        tool = registry.get(node.tool)
        if tool is None or set(node.arguments) - set(tool.args_model.model_fields):
            raise PlanInspectionError("unknown_tool_arguments")
        try:
            arguments = tool.args_model.model_validate(node.arguments).model_dump(mode="json")
        except ValidationError as exc:
            raise PlanInspectionError("invalid_tool_arguments") from exc
        normalized.append(
            {
                "id": node.id,
                "tool": node.tool,
                "arguments": arguments,
                "depends_on": sorted(a for a, b in pairs if b == node.id),
                "authorization": "not_checked_no_execution_authority",
            }
        )
    payload = {"nodes": normalized, "schema": "ezo-tool-plan-inspection-v1"}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **payload,
        "sha256": digest,
        "status": "static_inspection_only",
        "execution_authorized": False,
        "device_or_message_actions_attempted": False,
    }
