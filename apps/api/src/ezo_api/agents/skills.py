# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""SkillAgent: EZO grows new abilities — only with the owner's approval of the exact code.

"O'zingga kredit kalkulyatori vositasini qo'sh"   → EZO writes the code (draft); the owner
                                                    reviews it on the Ko'nikmalar page and
                                                    approves that exact code
"Kredit kalkulyatori: 50 mln, 24 oy, 22%"         → the approved skill runs in the locked
                                                    container (skill worker) and EZO answers
                                                    from its real output
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.llm import complete, extract_json
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.skills import service as skills

logger = logging.getLogger(__name__)

CREATE = re.compile(
    r"((yangi\s+)?(vosita|ko'nikma|qobiliyat|skill|tool|funksiya)\w*.{0,60}?(yoz|yarat|qo'sh|tuz|o'rgan|qil)|"
    r"o'zing(ga|ni).{0,60}?(qo'sh|o'rgat|kuchaytir|yarat)|"
    r"(create|build|write|add) (a |an |yourself )?(new )?(skill|tool)|"
    r"(создай|добавь|напиши) (себе )?(новый )?(навык|инструмент))"
)

INSTRUCTIONS = """Role: EZO's skills assistant (EZO writing small tools for itself).
- A new skill is only a DRAFT until the owner reviews its code on the “Ko‘nikmalar” page and approves it. Say so clearly; never say it can already be used.
- When a skill ran, answer ONLY from its real output in EZO's notes; if it failed or did not run, say so.
- Answer in the user's language."""

WRITE = """Write ONE small Python tool (a "skill") for EZO for what the user asks.
Reply with ONLY one JSON object: {"name": str (2-5 words in the user's language, e.g. "Kredit kalkulyatori"), "description": str, "input_hint": str (what run(data) expects: the keys, their meaning and one JSON example), "code": str}
Rules for "code":
- Define a top-level function run(data: dict) -> dict|list|str|int|float that does the whole job and returns a JSON-serialisable result.
- Only these imports: math, statistics, decimal, fractions, datetime, calendar, json, re, string, textwrap, itertools, functools, collections, dataclasses, typing, random, unicodedata, difflib, csv, io, operator, bisect, heapq, enum, zoneinfo.
- No files, network, input(), eval/exec, environment or system access (it runs in a locked container without them anyway).
- Validate the input and raise ValueError with a clear message when something is missing.
- Clear variable names; short comments in English; user-facing strings in the user's language."""

FILL = """Turn the user's message into the input of the skill below. Reply with ONLY one JSON object (the `data` for run(data)).
Skill: {name} — {description}
Input: {hint}
Use only values the message gives; if a needed value is missing, reply {{"__missing__": "what is missing"}}."""


def wants_new_skill(text: str) -> bool:
    return bool(CREATE.search(normalize(text)))


class SkillAgent(Agent):
    spec = AGENTS[Intent.SKILL]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(route="chat", context_mode="technical", instructions=INSTRUCTIONS,
                         steps=("detect", "draft_or_run", "generate"))  # fmt: skip

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        if tools.services.router.is_offline:
            gathered.notes.append(
                "No AI provider is connected, so EZO cannot write or fill a skill now. Say so."
            )
            return gathered
        skill = await skills.find_skill(tools.session, tools.user_id, ctx.turn.text)
        if skill is not None and not wants_new_skill(ctx.turn.text):
            await self._run(ctx, gathered, skill)
        else:
            await self._draft(ctx, gathered)
        return gathered

    async def _model_json(
        self,
        ctx: GatherContext,
        system: str,
        text: str,
        tool: str,
        gathered: Gathered,
        route: str = "chat",
    ) -> dict[str, Any] | None:
        try:
            completion = await complete(
                ctx.tools.services.router,
                route,
                system=system,
                messages=[ChatMessage("user", text[:20_000])],
                max_output_tokens=8_000,
                language=ctx.turn.language,
            )
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("%s failed: %s", tool, exc)
            gathered.tool_calls.append(
                {"tool": tool, "ok": False, "summary": "", "error": "AI provider failed"}
            )
            gathered.notes.append("The AI provider did not answer, so nothing was done. Say so.")
            return None
        data = extract_json(completion.text)
        gathered.tool_calls.append(
            {
                "tool": tool,
                "ok": data is not None,
                "summary": "",
                "error": None if data else "no JSON",
            }
        )
        if data is None:
            gathered.notes.append(
                "The model's answer could not be read, so nothing was saved. Say so and suggest trying again."
            )
        return data

    async def _draft(self, ctx: GatherContext, gathered: Gathered) -> None:
        data = await self._model_json(
            ctx, WRITE, ctx.turn.text, "write_skill", gathered, route="coding"
        )
        if data is None or not str(data.get("code") or "").strip():
            return
        skill = await skills.save_draft(
            ctx.tools.session, ctx.tools.user_id, name=str(data.get("name") or ""),
            description=str(data.get("description") or ""), input_hint=str(data.get("input_hint") or ""),
            code=str(data["code"]),
        )  # fmt: skip
        checks = skill.checks or {}
        gathered.notes.append(
            f"EZO wrote a skill DRAFT «{skill.name}»: {skill.description}. It is NOT usable yet: the owner opens the “Ko‘nikmalar” page, reads its code and presses “Ruxsat beraman” for exactly that code. "
            + (
                "The automatic checks passed."
                if checks.get("ok")
                else "The automatic checks FOUND PROBLEMS, so it cannot be approved as is: "
                + "; ".join(checks.get("problems", [])[:5])
                + "."
            )
            + f" After approval the user runs it by naming it, e.g. “{skill.name}: …”. It runs in a locked container without network."
        )

    async def _run(self, ctx: GatherContext, gathered: Gathered, skill: Any) -> None:
        tools = ctx.tools
        data = await self._model_json(
            ctx,
            FILL.format(name=skill.name, description=skill.description, hint=skill.input_hint),
            ctx.turn.text,
            "fill_skill_input",
            gathered,
        )
        if data is None:
            return
        if "__missing__" in data:
            gathered.notes.append(
                f"The skill «{skill.name}» needs more input: {data['__missing__']}. Ask for it."
            )
            return
        try:
            run = await skills.queue_run(tools.session, skill, data)
        except skills.SkillError as exc:
            gathered.notes.append(f"The skill «{skill.name}» cannot run: {exc.message}")
            return
        await tools.session.commit()  # the worker reads it from another connection
        if not tools.services.settings.skill_worker:
            gathered.notes.append(
                "The skill was queued, but the skill worker is not switched on in this installation (COMPOSE_PROFILES must include “skills”), so it did not run. Say so."
            )
            return
        if tools.on_activity is not None:
            tools.on_activity("working")
        finished = await skills.wait_for(tools.services.db.sessionmaker, run.id)
        if finished is None:
            gathered.notes.append(
                f"The skill «{skill.name}» did not finish in time (the skill worker may be busy or stopped). Say so."
            )
            return
        gathered.tool_calls.append(
            {
                "tool": "run_skill",
                "ok": finished.status == "completed",
                "summary": f"{skill.name} {finished.duration_ms} ms",
                "error": finished.error,
            }
        )
        if finished.status == "completed":
            gathered.notes.append(
                f"The skill «{skill.name}» ran in the locked container with input {data} and returned: {finished.output!r}. Present this result to the user clearly."
            )
        else:
            gathered.notes.append(
                f"The skill «{skill.name}» FAILED: {finished.error}. Say so; do not invent a result."
            )
