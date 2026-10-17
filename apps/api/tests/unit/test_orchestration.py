"""Native orchestration: plans, lifecycle, parallelism, approvals, failures, security."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from ezo_api.orchestration.base import MissionError, OrchestrationProvider, StepContext
from ezo_api.orchestration.complexity import assess, draft_plan
from ezo_api.orchestration.models import AgentOutput, MissionPlan, StepSpec
from ezo_api.orchestration.native import NativeOrchestrationProvider
from ezo_api.orchestration.registry import FALLBACK_NOTICE, select_orchestration
from ezo_api.orchestration.security import (
    child_env,
    is_allowed_tool,
    normalize_tool_name,
    redact_secrets,
)
from ezo_api.settings import Settings

USER = uuid.uuid4()


def plan(*steps: dict[str, Any]) -> MissionPlan:
    return MissionPlan(title="Test", goal="Test goal", steps=[StepSpec(**s) for s in steps])


def ok(summary: str, **extra: Any) -> AgentOutput:
    return AgentOutput(status="completed", summary=summary, **extra)


class Recorder:
    """A scripted executor that records what each step received."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.seen: dict[str, StepContext] = {}
        self.running = 0
        self.max_running = 0
        self.fail_times: dict[str, int] = {}
        self.raw: dict[str, Any] = {}

    async def __call__(self, context: StepContext) -> AgentOutput | dict[str, Any]:
        step = context.step.id
        self.seen[step] = context
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            if self.fail_times.get(step, 0) > 0:
                self.fail_times[step] -= 1
                raise RuntimeError(f"{step} broke with key sk-ant-abcdefghijklmnopqrstuv")
            if step in self.raw:
                return self.raw[step]  # type: ignore[no-any-return]
            return ok(f"{step} done", findings=[f"{step} finding"])
        finally:
            self.running -= 1


def test_native_provider_implements_the_interface() -> None:
    assert issubclass(NativeOrchestrationProvider, OrchestrationProvider)


@pytest.mark.parametrize(
    ("text", "mission"),
    [
        ("PDFni qisqartir.", False),
        ("Bugungi ob-havo haqida report yoz.", False),
        ("Hisobot asosida taqdimot tayyorla", False),
        ("Salom", False),
        ("20 ta competitorni o'rgan, biznes model tuz, 15 slayd pitch deck yarat.", True),
        (
            "Repo'ni audit qil: frontend/backend/security bo'yicha parallel analiz, keyin fix qil.",
            True,
        ),
        ("Ezo, startupimni boshidan oxirigacha tayyorla.", True),
        ("Ezo, bozorni o'rgan, competitorlarni top, website yarat va pitch deck qil.", True),
        ("Ezo, yangi davlat qarorini top, tahlil qil va professional hisobot tayyorla.", True),
    ],
)
def test_complexity_routing(text: str, mission: bool) -> None:
    assert assess(text).is_mission is mission


def test_draft_plan_orders_research_first_and_gates_code_changes() -> None:
    startup = draft_plan("Ezo, startupimni boshidan oxirigacha tayyorla.")
    ids = [s.id for s in startup.steps]
    assert ids[0] == "research" and ids[-1] == "qa"
    by_id = {s.id: s for s in startup.steps}
    assert set(by_id["presentation"].depends_on) == {"research", "business", "document"}
    assert len(startup.steps) <= 6  # anti-drift: a small team
    repo = draft_plan("Repo'ni audit qil, frontend/backend/security bo'yicha parallel analiz qil")
    reviews = [s for s in repo.steps if s.id.startswith("review_")]
    assert len(reviews) == 3 and all(not s.depends_on for s in reviews)
    fix = next(s for s in repo.steps if s.id == "developer")
    assert fix.requires_approval and "approval" in fix.approval_reason


def test_plan_validation() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        plan(
            {"id": "a", "title": "A", "agent_type": "research", "depends_on": ["b"]},
            {"id": "b", "title": "B", "agent_type": "document", "depends_on": ["a"]},
        )
    with pytest.raises(ValidationError, match="unknown"):
        plan({"id": "a", "title": "A", "agent_type": "research", "depends_on": ["zzz"]})
    with pytest.raises(ValidationError, match="approval_reason"):
        plan({"id": "a", "title": "A", "agent_type": "developer", "requires_approval": True})
    with pytest.raises(ValidationError):
        plan(*({"id": f"s{i}", "title": "S", "agent_type": "qa"} for i in range(13)))
    with pytest.raises(ValidationError):
        plan({"id": "Bad Id!", "title": "A", "agent_type": "qa"})


async def test_lifecycle_dependencies_parallelism_and_scoped_context() -> None:
    recorder = Recorder(delay=0.02)
    provider = NativeOrchestrationProvider(recorder)
    mission = await provider.start_mission(
        USER,
        plan(
            {"id": "research", "title": "Research", "agent_type": "research"},
            {
                "id": "business",
                "title": "Business",
                "agent_type": "business",
                "depends_on": ["research"],
            },
            {
                "id": "document",
                "title": "Report",
                "agent_type": "document",
                "depends_on": ["research"],
            },
            {
                "id": "deck",
                "title": "Deck",
                "agent_type": "presentation",
                "depends_on": ["business", "document"],
            },
            {"id": "qa", "title": "QA", "agent_type": "qa", "depends_on": ["deck"]},
        ),
    )
    await provider.wait(USER, mission.id)
    assert mission.status == "completed" and mission.progress == 1.0
    assert recorder.max_running == 2  # business and document ran in parallel
    assert set(recorder.seen["deck"].inputs) == {"business", "document"}  # only its dependencies
    assert recorder.seen["research"].inputs == {}
    order = [e.step_id for e in mission.events if e.kind == "step_started"]
    assert order[0] == "research" and order[-2:] == ["deck", "qa"]
    presences = [e.presence for e in mission.events if e.presence]
    assert presences[0] == "searching" and "creating" in presences and presences[-1] == "completed"
    result = await provider.get_result(USER, mission.id)
    assert result.status == "completed" and result.summary == "qa done"
    runs = await provider.list_agent_runs(USER, mission.id)
    assert [r["status"] for r in runs] == ["completed"] * 5


async def test_retry_then_success_and_failure_skips_dependents() -> None:
    recorder = Recorder()
    recorder.fail_times = {"a": 1, "b": 5}
    provider = NativeOrchestrationProvider(recorder)
    mission = await provider.start_mission(
        USER,
        plan(
            {"id": "a", "title": "A", "agent_type": "research", "max_retries": 1},
            {"id": "b", "title": "B", "agent_type": "document", "max_retries": 1},
            {"id": "c", "title": "C", "agent_type": "presentation", "depends_on": ["b"]},
            {"id": "qa", "title": "QA", "agent_type": "qa", "depends_on": ["a", "c"]},
        ),
    )
    await provider.wait(USER, mission.id)
    assert mission.step("a").status == "completed" and mission.step("a").attempts == 2
    assert mission.step("b").status == "failed" and mission.step("b").attempts == 2
    assert [mission.step(s).status for s in ("c", "qa")] == ["skipped", "skipped"]
    assert mission.status == "failed"  # never "completed" when a step failed
    # Secrets in errors are masked everywhere.
    assert "sk-ant" not in (mission.failure_reason or "")
    assert all("sk-ant" not in e.message for e in mission.events)
    assert mission.events[-1].presence == "error"
    result = await provider.get_result(USER, mission.id)
    assert result.skipped_steps == ["c", "qa"]


async def test_invalid_structured_output_and_timeouts_fail_the_step() -> None:
    recorder = Recorder()
    recorder.raw = {"bad": {"summary": "free text without a status"}}
    provider = NativeOrchestrationProvider(recorder)
    mission = await provider.start_mission(
        USER, plan({"id": "bad", "title": "Bad", "agent_type": "research", "max_retries": 0})
    )
    await provider.wait(USER, mission.id)
    assert mission.status == "failed"
    assert "does not match the contract" in (mission.step("bad").error or "")

    slow = NativeOrchestrationProvider(Recorder(delay=1.0), step_timeout=0.05)
    mission = await slow.start_mission(
        USER, plan({"id": "slow", "title": "Slow", "agent_type": "research", "max_retries": 0})
    )
    await slow.wait(USER, mission.id)
    assert mission.status == "failed" and mission.step("slow").error == "the agent took too long"


async def test_approval_gate_approve_and_reject() -> None:
    gated = plan(
        {"id": "review", "title": "Review", "agent_type": "developer"},
        {
            "id": "push",
            "title": "Push the fix",
            "agent_type": "developer",
            "depends_on": ["review"],
            "requires_approval": True,
            "approval_reason": "Pushes a branch to GitHub.",
        },
        {"id": "qa", "title": "QA", "agent_type": "qa", "depends_on": ["push"]},
    )
    recorder = Recorder()
    provider = NativeOrchestrationProvider(recorder)
    mission = await provider.start_mission(USER, gated)
    await provider.wait(USER, mission.id)
    assert mission.status == "waiting_for_user" and "push" not in recorder.seen
    [approval] = mission.approvals
    assert approval.reason == "Pushes a branch to GitHub." and approval.status == "pending"
    assert mission.events[-1].presence == "idle"
    await provider.submit_approval(USER, mission.id, approval.id, approved=True)
    await provider.wait(USER, mission.id)
    assert mission.status == "completed" and "push" in recorder.seen
    with pytest.raises(MissionError):  # an approval is decided once
        await provider.submit_approval(USER, mission.id, approval.id, approved=True)

    rejected = await provider.start_mission(USER, gated)
    await provider.wait(USER, rejected.id)
    await provider.submit_approval(USER, rejected.id, rejected.approvals[0].id, approved=False)
    await provider.wait(USER, rejected.id)
    assert rejected.step("push").status == "rejected" and rejected.step("qa").status == "skipped"
    assert rejected.status == "completed"
    assert (await provider.get_result(USER, rejected.id)).skipped_steps == ["push", "qa"]


async def test_pause_resume_and_cancel() -> None:
    steps = plan(
        {"id": "a", "title": "A", "agent_type": "research"},
        {"id": "b", "title": "B", "agent_type": "document", "depends_on": ["a"]},
    )
    provider = NativeOrchestrationProvider(Recorder(delay=0.05))
    mission = await provider.start_mission(USER, steps)
    await asyncio.sleep(0.01)  # step "a" is running now
    await provider.pause(USER, mission.id)  # takes effect after the running step
    await provider.wait(USER, mission.id)
    assert mission.status == "paused"
    assert mission.step("a").status == "completed" and mission.step("b").status == "pending"
    with pytest.raises(MissionError):
        await provider.get_result(USER, mission.id)
    await provider.resume(USER, mission.id)
    await provider.wait(USER, mission.id)
    assert mission.status == "completed"
    with pytest.raises(MissionError):
        await provider.resume(USER, mission.id)

    long = NativeOrchestrationProvider(Recorder(delay=5))
    running = await long.start_mission(USER, steps)
    await asyncio.sleep(0.05)
    await long.cancel(USER, running.id)
    assert running.status == "cancelled"
    assert [s.status for s in running.steps] == ["cancelled", "cancelled"]


async def test_missions_are_private_to_their_owner() -> None:
    provider = NativeOrchestrationProvider(Recorder())
    mission = await provider.start_mission(
        USER, plan({"id": "a", "title": "A", "agent_type": "research"})
    )
    with pytest.raises(MissionError, match="not found"):
        await provider.get_status(uuid.uuid4(), mission.id)
    with pytest.raises(MissionError):
        await provider.cancel(uuid.uuid4(), mission.id)


async def test_artifacts_from_steps_are_linked_to_the_mission() -> None:
    recorder = Recorder()
    recorder.raw = {
        "doc": ok("report", artifacts=[{"id": "a1", "title": "Report", "type": "document"}]),
        "deck": ok(
            "deck",
            artifacts=[
                {"id": "a2", "title": "Deck", "type": "presentation"},
                {"id": "a1", "title": "Report", "type": "document"},
            ],
        ),
    }
    provider = NativeOrchestrationProvider(recorder)
    mission = await provider.start_mission(
        USER,
        plan(
            {"id": "doc", "title": "Doc", "agent_type": "document"},
            {"id": "deck", "title": "Deck", "agent_type": "presentation", "depends_on": ["doc"]},
        ),
    )
    await provider.wait(USER, mission.id)
    assert [a.id for a in mission.artifacts] == ["a1", "a2"]


def test_tool_allow_list() -> None:
    for name in ("swarm_init", "mcp__ruflo__workflow_run", "agent_spawn"):
        assert is_allowed_tool(name)
    for name in (
        "terminal_execute",
        "mcp__ruflo__memory_store",
        "bash",
        "github_push",
        "",
        "swarm_init2",
    ):
        assert not is_allowed_tool(name)
    assert normalize_tool_name("mcp__claude-flow__agent_list") == "agent_list"


def test_secret_redaction() -> None:
    text = (
        "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz "
        "postgresql://ezo:supersecret@db:5432/ezo Authorization: Bearer abcdef1234567890xyz "
        "token ghp_abcdefghijklmnopqrstuvwxyz0123456789 GITHUB_TOKEN: abc123 normal words"
    )
    masked = redact_secrets(text)
    for secret in ("sk-ant-api03", "supersecret", "abcdef1234567890xyz", "ghp_", "abc123"):
        assert secret not in masked
    assert "postgresql://ezo:[redacted]@db:5432/ezo" in masked and "normal words" in masked


def test_child_env_never_copies_secrets() -> None:
    source = {"PATH": "/bin", "HOME": "/h", "ANTHROPIC_API_KEY": "sk-x", "DATABASE_URL": "pg://"}
    assert child_env({"RUFLO_FLAG": "1"}, source=source) == {
        "PATH": "/bin",
        "HOME": "/h",
        "RUFLO_FLAG": "1",
    }


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_ruflo_is_optional_and_falls_back_to_native() -> None:
    executor = Recorder()
    default = select_orchestration(_settings(), executor)
    assert default.provider.name == "native" and default.notice == ""
    disabled = select_orchestration(_settings(EZO_ORCHESTRATION_PROVIDER="ruflo"), executor)
    assert disabled.provider.name == "native" and disabled.notice == FALLBACK_NOTICE
    enabled = select_orchestration(
        _settings(
            EZO_ORCHESTRATION_PROVIDER="ruflo",
            EZO_RUFLO_ENABLED="true",
            EZO_RUFLO_COMMAND="npx ruflo mcp start",
        ),
        executor,
    )
    assert enabled.provider.name == "native" and enabled.notice == FALLBACK_NOTICE
