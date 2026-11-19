"""ComputerAgent: "Kalkulyatorni och", "Yuklamalar papkasida nima bor?", "https://… ni och".

The words are read without a model (`jarvis.pc.parse_pc_command`). EZO creates one JARVIS
task for the paired computer; it waits for the owner's approval of exactly that action (JARVIS
page or the computer's own dialog) before anything reaches the computer.
"""

from __future__ import annotations

import hashlib
import time

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.jarvis.pc import parse_pc_command
from ezo_api.jarvis.planner import PlanError, plan_document_workflow
from ezo_api.jarvis.service import JarvisError, JarvisService

INSTRUCTIONS = (
    "Role: EZO's computer assistant. Say in one or two sentences what EZO asked the paired "
    "computer to do and that it waits for the owner's approval (the JARVIS page or the "
    "computer's own dialog). Never say it was done unless EZO's notes say so. Answer in the "
    "user's language."
)


class ComputerAgent(Agent):
    spec = AGENTS[Intent.COMPUTER]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode="technical",
            instructions=INSTRUCTIONS,
            steps=("parse_command", "create_task", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        command = parse_pc_command(ctx.turn.text)
        workflow = None
        if command is None:
            try:
                workflow = plan_document_workflow(ctx.turn.text)
            except PlanError as exc:
                gathered.notes.append(
                    f"No computer action was recognised: {exc.message} Say so briefly."
                )
                return gathered
        key = hashlib.sha256(
            f"{tools.conversation_id}:{ctx.turn.text}:{int(time.time() // 60)}".encode()
        ).hexdigest()[:40]
        service = JarvisService(tools.session, tools.services)
        try:
            task = await service.create_task(
                tools.user_id, text=ctx.turn.text, idempotency_key=f"chat-{key}",
                language=ctx.turn.language,
            )  # fmt: skip
        except JarvisError as exc:
            gathered.tool_calls.append(
                {"tool": "jarvis_pc_task", "ok": False, "summary": "", "error": exc.message}
            )
            gathered.notes.append(
                f"EZO could not ask the computer: {exc.message} If no computer is paired, explain: "
                "install the EZO desktop app, then Settings → JARVIS → “Bu kompyuterni ulash”, and "
                "switch on “Kompyuterni boshqarish”."
            )
            return gathered
        gathered.tool_calls.append(
            {"tool": "jarvis_pc_task", "ok": True, "summary": str(task.id), "error": None}
        )
        if command is not None:
            what = command.description
        else:
            assert workflow is not None
            parts = ["take the newest file in Downloads"]
            if workflow.compare_previous:
                parts.append("compare it with the previous one")
            if workflow.percentages:
                parts.append("prepare the percentages")
            if workflow.convert_pdf:
                parts.append("make a PDF")
            if workflow.recipient:
                parts.append(f"send it by Telegram to «{workflow.recipient}»")
            what = (
                ", ".join(parts)
                + f" ({len(task.steps) if hasattr(task, 'steps') else 'several'} steps)"
            )
        gathered.notes.append(
            f"EZO created a JARVIS task for the paired computer: {what}. It is WAITING for the "
            "owner's approval (JARVIS page, or the dialog on that computer); nothing has run yet. "
            "Sending by Telegram is approved separately, for the exact recipient and files."
        )
        return gathered
