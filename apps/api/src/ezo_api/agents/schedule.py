# ruff: noqa: E501
"""ScheduleAgent (Jadval): "Har dushanba soat 9 da haftalik hisobot tayyorla",
"Har kuni 8:30 da muddatlarni eslat", "Jadvalimni ko'rsat", "Haftalik hisobotni to'xtat".

The words are read without a model (`schedule.requests`). A job runs in EZO's background
scheduler and keeps working after restarts; its results are on the Jadval page and, when the
owner asks, in their own linked Telegram chat. A job never messages other people.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import select

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.db.models import ScheduledJob, TelegramRecipient
from ezo_api.schedule import service as schedule
from ezo_api.schedule.requests import kind_of, parse, wants_list, wants_stop

SELF_LABELS = ("men", "o'zim", "ozim", "me", "myself", "owner", "я", "мен", "ўзим")

INSTRUCTIONS = (
    "Role: EZO's scheduler (Jadval). Say briefly what EZO scheduled, listed or stopped, using "
    "only EZO's notes (job names, times, next run). A scheduled job never messages other "
    "people. Answer in the user's language."
)


class ScheduleAgent(Agent):
    spec = AGENTS[Intent.SCHEDULE]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode="technical",
            instructions=INSTRUCTIONS,
            steps=("parse_request", "update_schedule", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        settings = tools.services.settings
        text = ctx.turn.text
        jobs = await schedule.jobs_for(tools.session, tools.user_id)
        if wants_stop(text):
            kind = kind_of(text)
            hit = [j for j in jobs if j.enabled and (kind is None or j.kind == kind)]
            for job in hit:
                job.enabled = False
            await tools.session.flush()
            gathered.notes.append(
                "EZO stopped: " + "; ".join(f"«{j.title}» ({schedule.when(j)})" for j in hit) + "."
                if hit
                else "No matching active scheduled job was found; nothing was stopped."
            )
            return gathered
        if wants_list(text) or kind_of(text) is None:
            gathered.notes.append(self._listing(jobs, settings.timezone))
            return gathered
        request = parse(text)
        assert request.kind is not None
        recipient_id = None
        telegram_note = ""
        if request.telegram:
            recipients = list(
                await tools.session.scalars(
                    select(TelegramRecipient).where(
                        TelegramRecipient.user_id == tools.user_id,
                        TelegramRecipient.status == "verified",
                    )
                )
            )
            own = [r for r in recipients if r.label.strip().lower() in SELF_LABELS]
            if own:
                recipient_id = own[0].id
                telegram_note = (
                    f" Results also go to the owner's own Telegram chat («{own[0].label}»)."
                )
            else:
                telegram_note = (
                    " Telegram delivery was NOT set: the owner has no linked Telegram chat named "
                    "«Men». Explain: on the JARVIS page add a recipient called «Men» and send /start "
                    "from your own Telegram; then choose it on the Jadval page."
                )
        job = await schedule.create_job(
            tools.session,
            tools.user_id,
            kind=request.kind,
            timezone=settings.timezone,
            weekdays=request.weekdays,
            at_time=request.at_time,
            month_day=request.month_day,
            notify_recipient_id=recipient_id,
        )
        gathered.tool_calls.append(
            {
                "tool": "schedule_job",
                "ok": True,
                "summary": f"{job.kind} {schedule.when(job)}",
                "error": None,
            }
        )
        local = job.next_run_at.astimezone(ZoneInfo(settings.timezone))
        gathered.notes.append(
            f"EZO scheduled «{job.title}» — {schedule.when(job)} ({settings.timezone}). "
            f"Next run: {local:%d.%m.%Y %H:%M}. It runs in the background even after a restart; "
            "results are on the «Jadval» page." + telegram_note
        )
        return gathered

    @staticmethod
    def _listing(jobs: list[ScheduledJob], timezone: str) -> str:
        from zoneinfo import ZoneInfo

        if not jobs:
            return (
                "The owner has no scheduled jobs. Examples they can say: «Har dushanba soat 9 da "
                "haftalik hisobot tayyorla», «Har kuni 8:30 da muddatlarni eslat»."
            )
        rows = []
        for job in jobs:
            nxt = job.next_run_at.astimezone(ZoneInfo(timezone))
            rows.append(
                f"«{job.title}» — {schedule.when(job)}, "
                + (f"next {nxt:%d.%m %H:%M}" if job.enabled else "STOPPED")
                + (f", last result: {job.last_status}" if job.last_status else "")
            )
        return "The owner's scheduled jobs: " + "; ".join(rows) + "."
