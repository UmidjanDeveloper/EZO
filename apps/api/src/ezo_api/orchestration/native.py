"""NativeOrchestrationProvider: EZO's own mission runner (always available, no dependencies).

Coordinator-led and deterministic:
- steps run as soon as their dependencies completed, up to MAX_PARALLEL_AGENTS at once;
- a step that needs approval waits (mission → ``waiting_for_user``) until the user decides;
- failures are retried ``max_retries`` times, then the step fails, its dependents are
  skipped and the mission ends ``failed`` — a mission is never reported completed when a
  step (including the final QA) did not succeed;
- pause takes effect between steps; cancel stops running steps immediately.

State is kept in memory for now (persistence: docs/RUFLO_INTEGRATION_PLAN.md).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from pydantic import ValidationError

from ezo_api.orchestration.base import (
    MissionError,
    OrchestrationProvider,
    StepContext,
    StepExecutor,
)
from ezo_api.orchestration.complexity import draft_plan
from ezo_api.orchestration.models import (
    MAX_PARALLEL_AGENTS,
    TERMINAL_MISSION,
    AgentOutput,
    Mission,
    MissionApproval,
    MissionEvent,
    MissionPlan,
    MissionResult,
    MissionStep,
    now,
)
from ezo_api.orchestration.security import redact_secrets

logger = logging.getLogger(__name__)

# Real activity → EZO orb state (web/lib/ezo-state.ts). Waiting for the user is not work.
PRESENCE: dict[str, str] = {
    "research": "searching",
    "legal_research": "searching",
    "business": "working",
    "document": "creating",
    "presentation": "creating",
    "visual": "creating",
    "developer": "coding",
    "qa": "working",
}
DEFAULT_STEP_TIMEOUT = 600.0
_BLOCKED = ("failed", "rejected", "skipped", "cancelled")


class NativeOrchestrationProvider(OrchestrationProvider):
    name = "native"

    def __init__(
        self,
        executor: StepExecutor,
        *,
        max_parallel: int = MAX_PARALLEL_AGENTS,
        step_timeout: float = DEFAULT_STEP_TIMEOUT,
    ) -> None:
        self._executor = executor
        self._max_parallel = max(1, min(max_parallel, MAX_PARALLEL_AGENTS))
        self._step_timeout = step_timeout
        self._missions: dict[uuid.UUID, Mission] = {}
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._approved: dict[uuid.UUID, set[str]] = {}

    # --- interface -------------------------------------------------------------------------

    async def plan_mission(self, goal: str) -> MissionPlan:
        return draft_plan(goal)

    async def start_mission(
        self, user_id: uuid.UUID, plan: MissionPlan, project_id: uuid.UUID | None = None
    ) -> Mission:
        mission = Mission(
            id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            plan=plan,
            orchestration_provider=self.name,
            steps=[MissionStep(spec, index) for index, spec in enumerate(plan.steps)],
        )
        self._missions[mission.id] = mission
        self._approved[mission.id] = set()
        self._event(mission, "created", f"Mission planned with {len(plan.steps)} steps.")
        mission.status = "running"
        mission.started_at = now()
        self._launch(mission)
        return mission

    async def get_status(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        return self._owned(user_id, mission_id)

    async def wait(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        """Wait until the mission stops (finished, paused or waiting for the user)."""
        mission = self._owned(user_id, mission_id)
        task = self._tasks.get(mission_id)
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(task)
        return mission

    async def pause(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        mission = self._owned(user_id, mission_id)
        self._require_active(mission)
        mission.metadata["pause_requested"] = True
        if not self._running(mission_id):
            self._set_paused(mission)
        return mission

    async def resume(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        mission = self._owned(user_id, mission_id)
        if mission.status != "paused":
            raise MissionError("not_paused", "Only a paused mission can be resumed.")
        mission.metadata.pop("pause_requested", None)
        mission.status = "running"
        self._event(mission, "resumed", "Mission resumed.")
        self._launch(mission)
        return mission

    async def cancel(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        mission = self._owned(user_id, mission_id)
        if mission.status in TERMINAL_MISSION:
            return mission
        task = self._tasks.get(mission_id)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for step in mission.steps:
            if step.status in ("pending", "running", "waiting_for_user"):
                step.status = "cancelled"
        for approval in mission.approvals:
            if approval.status == "pending":
                approval.status = "rejected"
                approval.note = "mission cancelled"
        mission.status = "cancelled"
        mission.completed_at = now()
        self._event(mission, "cancelled", "Mission cancelled by the user.")
        return mission

    async def submit_approval(
        self,
        user_id: uuid.UUID,
        mission_id: uuid.UUID,
        approval_id: uuid.UUID,
        approved: bool,
        note: str = "",
    ) -> Mission:
        mission = self._owned(user_id, mission_id)
        approval = next((a for a in mission.approvals if a.id == approval_id), None)
        if approval is None or approval.status != "pending":
            raise MissionError("not_found", "There is no pending approval with this id.")
        approval.status = "approved" if approved else "rejected"
        approval.decided_at = now()
        approval.note = note[:1_000]
        step = mission.step(approval.step_id)
        if approved:
            self._approved[mission.id].add(step.spec.id)
            step.status = "pending"
            self._event(mission, "approved", f"Approved: {approval.action}", step.spec.id)
        else:
            step.status = "rejected"
            step.completed_at = now()
            self._event(mission, "rejected", f"Rejected: {approval.action}", step.spec.id)
        if mission.status == "waiting_for_user":
            mission.status = "running"
            self._launch(mission)
        return mission

    async def list_agent_runs(
        self, user_id: uuid.UUID, mission_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        mission = self._owned(user_id, mission_id)
        return [
            {
                "step_id": step.spec.id,
                "agent_type": step.spec.agent_type,
                "status": step.status,
                "attempts": step.attempts,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
                "error": step.error,
            }
            for step in mission.steps
        ]

    async def get_result(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> MissionResult:
        mission = self._owned(user_id, mission_id)
        if mission.status not in TERMINAL_MISSION:
            raise MissionError("not_finished", "The mission has not finished yet.")
        outputs = {s.spec.id: s.output for s in mission.steps if s.output is not None}
        final = outputs.get("qa") or (list(outputs.values())[-1] if outputs else None)
        return MissionResult(
            mission_id=mission.id,
            status=mission.status,
            summary=final.summary
            if mission.status == "completed" and final
            else (mission.failure_reason or f"Mission {mission.status}."),
            outputs=outputs,
            artifacts=mission.artifacts,
            skipped_steps=[s.spec.id for s in mission.steps if s.status in ("rejected", "skipped")],
            failure_reason=mission.failure_reason,
        )

    # --- engine ----------------------------------------------------------------------------

    def _owned(self, user_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
        mission = self._missions.get(mission_id)
        if mission is None or mission.user_id != user_id:
            raise MissionError("not_found", "Mission not found.")
        return mission

    def _require_active(self, mission: Mission) -> None:
        if mission.status in TERMINAL_MISSION:
            raise MissionError("finished", "The mission has already finished.")

    def _running(self, mission_id: uuid.UUID) -> bool:
        task = self._tasks.get(mission_id)
        return task is not None and not task.done()

    def _launch(self, mission: Mission) -> None:
        if not self._running(mission.id):
            self._tasks[mission.id] = asyncio.create_task(self._run(mission))

    def _event(self, mission: Mission, kind: str, message: str, step_id: str | None = None) -> None:
        presence = {
            "step_started": PRESENCE.get(
                mission.step(step_id).spec.agent_type if step_id else "", "working"
            ),
            "waiting_for_user": "idle",
            "completed": "completed",
            "failed": "error",
        }.get(kind)
        mission.events.append(MissionEvent(kind, redact_secrets(message), step_id, presence))

    def _set_paused(self, mission: Mission) -> None:
        mission.status = "paused"
        self._event(mission, "paused", "Mission paused.")

    async def _run(self, mission: Mission) -> None:
        while True:
            self._skip_blocked(mission)
            if mission.metadata.get("pause_requested"):
                self._set_paused(mission)
                return
            ready = [
                step
                for step in mission.steps
                if step.status == "pending"
                and all(mission.step(d).status == "completed" for d in step.spec.depends_on)
            ]
            runnable = []
            for step in ready:
                if step.spec.requires_approval and step.spec.id not in self._approved[mission.id]:
                    self._request_approval(mission, step)
                else:
                    runnable.append(step)
            if runnable:
                await asyncio.gather(
                    *(self._run_step(mission, step) for step in runnable[: self._max_parallel])
                )
                continue
            if any(step.status == "waiting_for_user" for step in mission.steps):
                mission.status = "waiting_for_user"
                self._event(mission, "waiting_for_user", "Waiting for your approval.")
                return
            self._finish(mission)
            return

    def _skip_blocked(self, mission: Mission) -> None:
        changed = True
        while changed:
            changed = False
            for step in mission.steps:
                if step.status == "pending" and any(
                    mission.step(d).status in _BLOCKED for d in step.spec.depends_on
                ):
                    step.status = "skipped"
                    step.completed_at = now()
                    self._event(
                        mission, "step_skipped", f"Skipped: {step.spec.title}", step.spec.id
                    )
                    changed = True

    def _request_approval(self, mission: Mission, step: MissionStep) -> None:
        if step.status == "waiting_for_user":
            return
        step.status = "waiting_for_user"
        mission.approvals.append(
            MissionApproval(
                id=uuid.uuid4(),
                step_id=step.spec.id,
                action=step.spec.title,
                reason=step.spec.approval_reason,
            )
        )
        self._event(
            mission, "approval_requested", f"Approval needed: {step.spec.title}", step.spec.id
        )

    async def _run_step(self, mission: Mission, step: MissionStep) -> None:
        context = StepContext(
            mission_id=mission.id,
            user_id=mission.user_id,
            project_id=mission.project_id,
            goal=mission.plan.goal,
            step=step.spec,
            inputs={
                dep: output
                for dep in step.spec.depends_on
                if (output := mission.step(dep).output) is not None
            },
        )
        step.status = "running"
        step.started_at = now()
        self._event(mission, "step_started", f"Started: {step.spec.title}", step.spec.id)
        while True:
            step.attempts += 1
            try:
                raw = await asyncio.wait_for(self._executor(context), self._step_timeout)
                output = raw if isinstance(raw, AgentOutput) else AgentOutput.model_validate(raw)
                if output.status != "completed":
                    detail = "; ".join(output.errors) or output.summary
                    raise RuntimeError(f"agent reported {output.status}: {detail}")
                step.output = output
                step.status = "completed"
                step.completed_at = now()
                step.error = None
                self._event(mission, "step_completed", f"Done: {step.spec.title}", step.spec.id)
                return
            except asyncio.CancelledError:
                step.status = "cancelled"
                raise
            except Exception as exc:
                if isinstance(exc, TimeoutError):
                    reason = "the agent took too long"
                elif isinstance(exc, ValidationError):
                    reason = "the agent returned output that does not match the contract"
                else:
                    reason = str(exc) or type(exc).__name__
                step.error = redact_secrets(reason)[:1_000]
                logger.warning(
                    "Mission step %s attempt %s failed: %s", step.spec.id, step.attempts, step.error
                )
                if step.attempts > step.spec.max_retries:
                    step.status = "failed"
                    step.completed_at = now()
                    self._event(
                        mission,
                        "step_failed",
                        f"Failed: {step.spec.title} ({step.error})",
                        step.spec.id,
                    )
                    return
                self._event(mission, "step_retry", f"Retrying: {step.spec.title}", step.spec.id)

    def _finish(self, mission: Mission) -> None:
        failed = [s for s in mission.steps if s.status == "failed"]
        incomplete = [s for s in mission.steps if s.status != "completed"]
        mission.completed_at = now()
        if failed:
            mission.status = "failed"
            mission.failure_reason = "; ".join(f"{s.spec.title}: {s.error}" for s in failed)[:2_000]
            self._event(mission, "failed", f"Mission failed: {mission.failure_reason}")
        elif incomplete:
            rejected = [s for s in incomplete if s.status == "rejected"]
            mission.status = "cancelled" if rejected else "failed"
            mission.failure_reason = (
                "Required approval rejected: " + "; ".join(s.spec.title for s in rejected)
                if rejected
                else "Mission did not complete all required steps."
            )[:2_000]
            self._event(mission, mission.status, mission.failure_reason)
        else:
            mission.status = "completed"
            self._event(mission, "completed", "Mission completed.")
