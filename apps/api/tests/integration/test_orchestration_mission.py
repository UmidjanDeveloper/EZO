"""A realistic native mission with EZO's real tools and artifacts (no paid API, no Ruflo).

Research (deterministic stand-in) → DocumentAgent tools write a report from the research
output → presentation tools build a deck from both structured outputs → QA verifies the
artifacts exist. The mission must complete and link both artifacts.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from ezo_api.db.models import Artifact
from ezo_api.orchestration.base import StepContext
from ezo_api.orchestration.complexity import assess, draft_plan
from ezo_api.orchestration.models import AgentOutput
from ezo_api.orchestration.native import NativeOrchestrationProvider
from ezo_api.services import Services
from ezo_api.tools.base import ToolContext

GOAL = (
    "Ezo, “Choynak AI” degan xayoliy mahsulot bozorini o'rgan, qisqa hisobot va "
    "taqdimot rejasini tayyorla"
)
FINDINGS = [
    "Choynak AI — choyxonalar uchun buyurtma yordamchisi (xayoliy mahsulot).",
    "Asosiy mijozlar: Toshkentdagi 40 ta choyxona (test ma'lumoti).",
    "Raqobatchilar: qog'oz menyu va umumiy POS tizimlari.",
]


def make_executor(services: Services, user_id: uuid.UUID) -> Any:
    seen: dict[str, StepContext] = {}

    async def run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with services.db.sessionmaker() as session:
            ctx = ToolContext(session=session, services=services, user_id=user_id)
            result = await services.tools.execute(name, arguments, ctx)
            await session.commit()
        assert result.ok, result.error
        return result.data  # type: ignore[no-any-return]

    async def execute(context: StepContext) -> AgentOutput:
        seen[context.step.id] = context
        step = context.step.agent_type
        if step == "research":
            return AgentOutput(
                status="completed",
                summary="Bozor bo'yicha 3 ta asosiy topilma.",
                findings=FINDINGS,
                sources=[{"title": "Test ma'lumotlari", "kind": "file"}],
            )
        if step == "document":
            research = context.inputs["research"]
            markdown = "# Choynak AI hisoboti\n\n## Topilmalar\n\n" + "\n".join(
                f"- {f}" for f in research.findings
            )
            data = await run_tool(
                "create_document", {"title": "Choynak AI hisoboti", "markdown": markdown}
            )
            return AgentOutput(
                status="completed",
                summary=f"Hisobot: {data['words']} so'z.",
                findings=research.findings[:2],
                artifacts=[data["artifact"]],
            )
        if step == "presentation":
            research = context.inputs["research"]
            report = context.inputs["document"]
            deck = {
                "title": "Choynak AI",
                "slides": [
                    {"layout": "cover", "title": "Choynak AI", "subtitle": report.summary},
                    {"layout": "bullets", "title": "Topilmalar", "bullets": research.findings},
                    {"layout": "closing", "title": "Rahmat"},
                ],
            }
            data = await run_tool("create_presentation", {"deck": deck})
            return AgentOutput(
                status="completed",
                summary=f"Taqdimot: {data['slides']} slayd, QA: {data['qa']['passed']}.",
                artifacts=[data["artifact"]],
            )
        # QA: every artifact the mission reported must really exist and be ready.
        async with services.db.sessionmaker() as session:
            ids = [a.id for out in context.inputs.values() for a in out.artifacts]
            found = [await session.get(Artifact, uuid.UUID(i)) for i in ids]
        missing = [i for i, a in zip(ids, found, strict=True) if a is None or a.status != "ready"]
        return AgentOutput(
            status="failed" if missing or not ids else "completed",
            summary=f"QA: {len(ids)} artifact(s) checked.",
            errors=[f"missing {m}" for m in missing],
        )

    execute.seen = seen  # type: ignore[attr-defined]
    return execute


async def test_research_document_presentation_mission(client: AsyncClient, app: FastAPI) -> None:
    services: Services = app.state.services
    user_id = uuid.UUID((await client.get("/api/me")).json()["id"])
    complexity = assess(GOAL)
    assert complexity.is_mission and set(complexity.roles) >= {
        "research",
        "document",
        "presentation",
    }
    plan = draft_plan(GOAL, complexity)
    assert [s.id for s in plan.steps] == ["research", "document", "presentation", "qa"]

    executor = make_executor(services, user_id)
    provider = NativeOrchestrationProvider(executor)
    mission = await provider.start_mission(user_id, plan)
    await provider.wait(user_id, mission.id)

    assert mission.status == "completed", mission.failure_reason
    seen = executor.seen
    assert seen["document"].inputs["research"].findings == FINDINGS  # structured hand-off
    assert set(seen["presentation"].inputs) == {"research", "document"}
    assert [a.type for a in mission.artifacts] == ["document", "presentation"]

    listed = (await client.get("/api/artifacts")).json()
    assert {a["id"] for a in listed} == {a.id for a in mission.artifacts}
    deck = next(a for a in listed if a["type"] == "presentation")
    assert deck["current_version"]["generation_metadata"]["slides"] == 3
    result = await provider.get_result(user_id, mission.id)
    assert result.summary == "QA: 2 artifact(s) checked." and not result.skipped_steps
