# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""DistrictAgent: the district center in chat.

    "Xatlov qalay ketyapti?"              → reads the project's official API (if due),
                                            answers from the stored numbers: totals,
                                            pace against the deadline, who is behind
    "Nega Aliyev xatlov qilmayapti,
     uni ogohlantir"                       → a warning DRAFT for that person, shown as a
                                            card; nothing is sent until the owner presses
                                            "Yuborish" (Telegram and/or SMS)
    "Orqada qolganlarni ogohlantir"        → one draft per person who is behind (max 20)

Numbers come only from the database; the model never invents them.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.models import DistrictAssignment, DistrictMember, DistrictProject
from ezo_api.district import service as district
from ezo_api.district.progress import describe

WARN = re.compile(
    r"\b(ogohlantir\w*|eslat\w*|tanbeh\w*|sms\s+(yubor|jo'nat|tashla)\w*|xabar\s+(yubor|jo'nat|ber)\w*|"
    r"огоҳлантир\w*|предупреди\w*|напомни\w*|отправь\s+смс|warn\w*|remind\w*|send (an? )?(sms|message))"
)
BEHIND = re.compile(
    r"\b(orqada qol\w*|ortda qol\w*|bajarmagan\w*|qilmagan\w*|qilmayotgan\w*|barcha\w*|hammas\w*|"
    r"отста\w*|все[мх]?\b|behind|everyone|all of them)"
)
GENERAL_STATUS = re.compile(
    r"\b(loyihalar\w*|barcha loyiha\w*|tuman loyiha\w*|hokimlik loyiha\w*|проект\w*|projects)\b"
)

INSTRUCTIONS = """Role: EZO's district center assistant for the hokimiyat (district administration).
- Answer ONLY from the numbers in EZO's notes (they come from the official API, an imported table or manual entries). Never invent people, numbers or dates. If a number is missing, say so.
- Be brief and concrete: overall progress, pace against the deadline, then who is behind (name, area, done of plan).
- Warnings: EZO only prepared DRAFTS. Say clearly that nothing was sent yet and that the owner must check the text and press “Yuborish” on the card under this message. Never say a message was sent unless the notes say it was.
- Personal data (phones) are not repeated in the answer.
- Answer in the user's language."""


def wants_district(text: str, project_names: list[str]) -> bool:
    """The message is about one of the account's district projects (or all of them)."""
    norm = normalize(text)
    if GENERAL_STATUS.search(norm) and re.search(
        r"\b(holat|qalay|qanday|natija|hisobot|статус|как идут|status)", norm
    ):
        return True
    stems = district._stems(text)
    return any(district._stems(name) & stems for name in project_names)


class DistrictAgent(Agent):
    spec = AGENTS[Intent.DISTRICT]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode="professional",
            instructions=INSTRUCTIONS,
            steps=("match_project", "sync_source", "status", "draft_notices", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        db = tools.session

        text = ctx.turn.text
        rows = await district.projects(db, tools.user_id)
        if not rows:
            gathered.notes.append(
                "The user has no district projects in EZO yet. Explain in 2–3 lines that they can add one on the “Tuman markazi” page (name, plan per person, deadline) and fill it from the official API, an Excel/CSV table or by hand."
            )
            return gathered
        matched = district.match_projects(text, rows)
        if not matched and ctx.history_hint:
            matched = district.match_projects(ctx.history_hint, rows)
        if not matched:
            matched = [r for r in rows if r.status == "active"][:5]
            gathered.notes.append("No project was named, so all active projects are summarised.")
        warn = bool(WARN.search(normalize(text)))
        for row in matched[:5]:
            await self._project(ctx, gathered, row, warn=warn and len(matched) == 1)
        if warn and len(matched) > 1:
            gathered.notes.append(
                "Several projects match, so no warning was drafted: ask which project (names: "
                + ", ".join(f"«{r.name}»" for r in matched[:5])
                + ")."
            )
        await db.flush()
        return gathered

    async def _project(
        self, ctx: GatherContext, gathered: Gathered, row: DistrictProject, *, warn: bool
    ) -> None:
        tools = ctx.tools
        db = tools.session
        settings = tools.services.settings
        synced = await district.sync(db, row, settings, tools.services.fetcher)
        gathered.tool_calls.append(
            {
                "tool": "district_status",
                "ok": True,
                "summary": f"{row.name}: " + ("synced" if synced else row.source_kind),
                "error": None,
            }
        )
        status = await district.status(db, row, settings)
        source = {
            "api": f"the official API (last read {row.last_sync_at:%Y-%m-%d %H:%M} UTC)"
            if row.last_sync_at
            else "the official API (not read yet)",
            "import": "the last imported table",
            "manual": "manual entries",
        }[row.source_kind]
        lines = [describe(status), f"Source of the numbers: {source}."]
        if row.last_sync_error:
            lines.append(
                f"The last API read FAILED: {row.last_sync_error} — say the numbers may be out of date."
            )
        if row.responsible_org:
            lines.append(f"Responsible organisation: {row.responsible_org}.")
        gathered.notes.append("\n".join(lines))
        if not warn:
            return
        people = list(
            await db.scalars(
                select(DistrictMember)
                .join(DistrictAssignment, DistrictAssignment.member_id == DistrictMember.id)
                .where(DistrictAssignment.project_id == row.id)
            )
        )
        targets = district.match_people(ctx.turn.text, people)
        if not targets and BEHIND.search(normalize(ctx.turn.text)):
            behind_ids = {p.member_id for p in status.behind}
            targets = [p for p in people if str(p.id) in behind_ids]
        if not targets:
            gathered.notes.append(
                "The user asked for a warning but EZO could not tell to whom: no person of this project was named and nobody is behind. Ask who should be warned."
            )
            return
        drafts = []
        by_member = {
            a.member_id: a
            for a in await db.scalars(
                select(DistrictAssignment).where(DistrictAssignment.project_id == row.id)
            )
        }
        for person in targets[: district.MAX_DRAFTS_PER_TURN]:
            notice = await district.draft(db, settings, row, person, by_member.get(person.id))
            drafts.append(notice)
            gathered.notices.append(district.notice_out(notice))
        gathered.tool_calls.append(
            {
                "tool": "district_draft_notices",
                "ok": True,
                "summary": f"{len(drafts)} draft(s)",
                "error": None,
            }
        )
        no_channel = [d.recipient_name for d in drafts if not d.channels]
        note = (
            f"EZO prepared {len(drafts)} warning DRAFT(S) (NOT sent): "
            + "; ".join(
                f"{d.recipient_name} via {', '.join(d.channels) or 'no channel yet'}"
                for d in drafts
            )
            + ". The cards under this message show the exact text; the owner reviews it and presses “Yuborish”."
        )
        if len(targets) > district.MAX_DRAFTS_PER_TURN:
            note += f" Only the first {district.MAX_DRAFTS_PER_TURN} of {len(targets)} people got a draft."
        if no_channel:
            note += (
                " No way to reach: "
                + ", ".join(no_channel)
                + " — add a phone number (for SMS through Eskiz) or link their Telegram on the Tuman markazi page."
            )
        gathered.notes.append(note)
