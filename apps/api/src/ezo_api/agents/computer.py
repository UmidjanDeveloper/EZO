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
        if command is None:
            gathered.notes.append("No computer action was recognised. Say so briefly.")
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
        gathered.notes.append(
            f"EZO created a JARVIS task for the paired computer: {command.description}. It is "
            "WAITING for the owner's approval (JARVIS page, or the dialog on that computer); "
            "nothing has run yet."
        )
        return gathered
