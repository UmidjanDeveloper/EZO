# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""ChanceryAgent (Devonxona): the hokimiyat's appeals, meetings, tasks and reports in chat.

    "Yangi murojaat: Karimov Aziz, Navbahor MFY, ko'cha chirog'i yonmayapti, virtual qabulxona"
                                    → registered as M-2026-0001, due in 15 days
    "M-2026-0001 ga javob xati tayyorla"       → reply letter on the letterhead (Word)
    "M-2026-0001 ga javob berildi"             → marked answered
    "Yig'ilish bayonnomasini tuz: <notes>"     → minutes (Word) + every task in the register
    "T-2026-0003 bajarildi"                    → task done
    "Muddati o'tganlarni eslat"                → warning drafts to the people responsible
    "Haftalik hisobot tayyorla"                → report (Word) from appeals, tasks and projects
    anything else                              → what is overdue and due soon

Numbers, dates and states come from the database; the model only extracts fields from the
user's own words and drafts text, and every draft is checked before it is saved.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered, call_tool
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.llm import complete, extract_json
from ezo_api.chancery import service as office
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.models import Appeal, DistrictMember, DistrictNotice, GovTask
from ezo_api.district import service as district
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage

logger = logging.getLogger(__name__)

APPEAL_NUMBER = re.compile(r"\bm-\d{4}-\d{4}\b")
TASK_NUMBER = re.compile(r"\bt-\d{4}-\d{4}\b")
_REGISTER = re.compile(
    r"(yangi murojaat|murojaat\w*\s+(ro'yxatga ol|qayd et|kirit|qo'sh|ro'yxatla)|register (an? )?appeal|новое обращение|зарегистрируй обращение)"
)
_ANSWER_LETTER = re.compile(
    r"(javob\s*(xati|xat)?\s*\w*\s*(tayyorla|yoz|loyiha)|draft (a |the )?(reply|answer)|ответ\w*\s*(подготовь|напиши))"
)
_ANSWERED = re.compile(
    r"(javob berildi|javob qaytarildi|hal qilindi|yopildi|answered|closed|ответ дан|закрыто)"
)
_MINUTES = re.compile(r"(bayonnoma|protokol|протокол|minutes)")
_DONE = re.compile(r"(bajarildi|bajardi|tugatildi|done|completed|выполнено)")
_REMIND = re.compile(r"(eslat|ogohlantir|напомни|предупреди|remind|warn)")
_REPORT = re.compile(
    r"((haftalik|oylik|kunlik|yillik)\s+hisobot|hisobot\s+(tayyorla|tuz|yoz)|weekly report|monthly report|недельн\w* отчет|месячн\w* отчет)"
)
_MONTH = re.compile(r"(oylik|monthly|месячн)")

INSTRUCTIONS = """Role: EZO's devonxona (office) assistant for the hokimiyat.
- Report ONLY what EZO's notes say was registered, changed or found: numbers, dates, people and states are facts from the database. Never invent appeals, tasks, deadlines or people.
- Warnings are DRAFTS until the owner presses “Yuborish” on the card; never say a message was sent unless the notes say so.
- Be brief and businesslike; list overdue items first.
- Answer in the user's language."""

EXTRACT_APPEAL = """Extract one citizen appeal (murojaat) from the user's message. Today is {today}.
Reply with ONLY one JSON object:
{{"applicant": str (person or organisation name, as written), "contact": str (address/MFY/phone as written, or ""), "channel": "virtual_reception"|"president_portal"|"written"|"oral"|"phone"|"other", "summary": str (what they ask or complain about, one or two sentences in the user's language), "received_on": "YYYY-MM-DD" or null (null = today), "due_on": "YYYY-MM-DD" or null (only if the user names a deadline), "assignee": str (who should handle it, as written, or "")}}
Use only what the message says; leave a field empty or null when it is not given."""

EXTRACT_MINUTES = """Turn the user's meeting notes into structured minutes. Today is {today}.
Reply with ONLY one JSON object:
{{"title": str, "held_on": "YYYY-MM-DD" or null, "chair": str, "attendees": [str], "agenda": [str], "discussion": [str], "decisions": [str], "tasks": [{{"title": str, "assignee": str, "due_on": "YYYY-MM-DD" or null}}]}}
Rules: use ONLY what the notes say (no invented names, numbers or dates); turn relative deadlines ("juma kuni", "bir hafta ichida") into dates from today; write in the notes' language; every instruction to someone is a task."""

LETTER = """Write the body of an official reply letter from the hokimiyat to a citizen's appeal, in Uzbek (Latin), formal and polite.
Use ONLY the facts below and the user's instructions; do not promise anything the instructions do not say; no invented dates, sums or articles of law.
Structure: salutation to the applicant; reference to their appeal (number and date); the answer; closing sentence. Plain paragraphs, no headings, no signature block (the letterhead adds it)."""


def _date(value: Any, fallback: date | None = None) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return fallback
    return fallback


def wants_chancery(text: str) -> bool:
    norm = normalize(text)
    return bool(APPEAL_NUMBER.search(norm) or TASK_NUMBER.search(norm))


class ChanceryAgent(Agent):
    spec = AGENTS[Intent.CHANCERY]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode="professional",
            instructions=INSTRUCTIONS,
            steps=("detect_action", "act", "compose_prompt", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        norm = normalize(ctx.turn.text)
        on = office.today(ctx.tools.services.settings.timezone)
        appeal_no = APPEAL_NUMBER.search(norm)
        task_no = TASK_NUMBER.search(norm)
        if appeal_no and _ANSWER_LETTER.search(norm):
            await self._reply_letter(ctx, gathered, appeal_no.group(0), on)
        elif appeal_no and _ANSWERED.search(norm):
            await self._set_appeal(ctx, gathered, appeal_no.group(0), on)
        elif task_no and _DONE.search(norm):
            await self._task_done(ctx, gathered, task_no.group(0), on)
        elif _REGISTER.search(norm):
            await self._register(ctx, gathered, on)
        elif _MINUTES.search(norm) and len(ctx.turn.text) >= 80:
            await self._minutes(ctx, gathered, on)
        elif _REPORT.search(norm):
            await self._report(ctx, gathered, on, monthly=bool(_MONTH.search(norm)))
        elif _REMIND.search(norm):
            await self._remind(ctx, gathered, on)
        else:
            await self._overview(ctx, gathered, on)
        await ctx.tools.session.flush()
        return gathered

    # --- helpers ------------------------------------------------------------------------

    async def _json(
        self, ctx: GatherContext, gathered: Gathered, system: str, text: str, tool: str
    ) -> dict[str, Any] | None:
        services = ctx.tools.services
        if services.router.is_offline:
            gathered.notes.append(
                "No AI provider is connected, so EZO cannot read this request now. Say so briefly."
            )
            return None
        try:
            completion = await complete(
                services.router,
                "chat",
                system=system,
                messages=[ChatMessage("user", text[:30_000])],
                max_output_tokens=6_000,
                language=ctx.turn.language,
            )
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("%s failed: %s", tool, exc)
            gathered.tool_calls.append(
                {"tool": tool, "ok": False, "summary": "", "error": "AI provider failed"}
            )
            gathered.notes.append("The AI provider did not answer, so nothing was saved. Say so.")
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
                "EZO could not read the request into fields, so nothing was saved. Ask the user to state it more clearly."
            )
        return data

    # --- actions ----------------------------------------------------------------------------

    async def _register(self, ctx: GatherContext, gathered: Gathered, on: date) -> None:
        data = await self._json(
            ctx,
            gathered,
            EXTRACT_APPEAL.format(today=on.isoformat()),
            ctx.turn.text,
            "extract_appeal",
        )
        if data is None:
            return
        received = _date(data.get("received_on"), on) or on
        if received > on:
            received = on
        try:
            appeal = await office.create_appeal(
                ctx.tools.session, ctx.tools.user_id,
                applicant=str(data.get("applicant") or ""), summary=str(data.get("summary") or ""),
                contact=str(data.get("contact") or ""), channel=str(data.get("channel") or "other"),
                received_on=received, due_on=_date(data.get("due_on")), assignee=str(data.get("assignee") or ""),
            )  # fmt: skip
        except office.ChanceryError as exc:
            gathered.notes.append(
                f"The appeal was NOT registered: {exc.message} Ask for the missing part."
            )
            return
        gathered.tool_calls.append(
            {"tool": "register_appeal", "ok": True, "summary": appeal.number, "error": None}
        )
        gathered.notes.append(
            "Registered: "
            + office.describe_appeal(appeal, on)
            + (
                " The handler is not one of the district's known people, so warnings cannot reach them until added on the Tuman markazi page."
                if appeal.assignee_name and appeal.assignee_member_id is None
                else ""
            )
            + f" Default deadline is {office.APPEAL_DAYS} days after receipt; the user can change it on the Devonxona page."
        )

    async def _set_appeal(
        self, ctx: GatherContext, gathered: Gathered, number: str, on: date
    ) -> None:
        appeal = await office.appeal_by_number(ctx.tools.session, ctx.tools.user_id, number)
        if appeal is None:
            gathered.notes.append(f"There is no appeal {number.upper()}. Say so.")
            return
        appeal.status, appeal.answered_on = "answered", on
        gathered.tool_calls.append(
            {
                "tool": "update_appeal",
                "ok": True,
                "summary": f"{appeal.number} answered",
                "error": None,
            }
        )
        gathered.notes.append("Marked as answered: " + office.describe_appeal(appeal, on))

    async def _task_done(
        self, ctx: GatherContext, gathered: Gathered, number: str, on: date
    ) -> None:
        task = await ctx.tools.session.scalar(
            select(GovTask).where(
                GovTask.user_id == ctx.tools.user_id, GovTask.number == number.upper()
            )
        )
        if task is None:
            gathered.notes.append(f"There is no task {number.upper()}. Say so.")
            return
        task.status, task.done_on = "done", on
        gathered.tool_calls.append(
            {"tool": "update_task", "ok": True, "summary": f"{task.number} done", "error": None}
        )
        gathered.notes.append("Marked as done: " + office.describe_task(task, on))

    async def _reply_letter(
        self, ctx: GatherContext, gathered: Gathered, number: str, on: date
    ) -> None:
        tools = ctx.tools
        appeal = await office.appeal_by_number(tools.session, tools.user_id, number)
        if appeal is None:
            gathered.notes.append(f"There is no appeal {number.upper()}. Say so.")
            return
        if tools.services.router.is_offline:
            gathered.notes.append(
                "No AI provider is connected, so EZO cannot draft the letter now. Say so."
            )
            return
        facts = (
            f"Appeal {appeal.number}, received {appeal.received_on:%d.%m.%Y} via {office.CHANNEL_NAMES[appeal.channel]}.\n"
            f"Applicant: {appeal.applicant}. Contact: {appeal.contact or '-'}.\n"
            f"What they asked: {appeal.summary}\n\nThe user's instructions for the answer: {ctx.turn.text}"
        )
        try:
            completion = await complete(
                tools.services.router,
                "chat",
                system=LETTER,
                messages=[ChatMessage("user", facts)],
                max_output_tokens=3_000,
                language="uz",
            )
        except (AllProvidersFailedError, StreamInterruptedError):
            gathered.notes.append("The AI provider did not answer, so no letter was made. Say so.")
            return
        body = completion.text.strip()
        heading = (
            f"# {appeal.applicant}ga\n\n*{appeal.contact}*\n\n"
            if appeal.contact
            else f"# {appeal.applicant}ga\n\n"
        )
        result = await call_tool(gathered, tools, "create_document", {
            "title": f"{appeal.number} — javob xati", "markdown": heading + body, "format": "docx",
            "letterhead": True, "metadata": {"action": "appeal_reply", "appeal": appeal.number},
            "provider": completion.provider, "model": completion.model,
        })  # fmt: skip
        if result.ok:
            artifact = result.data["artifact"]
            gathered.artifacts.append(artifact)
            appeal.answer_artifact_id = uuid.UUID(artifact["id"])
            appeal.answer = body[:20_000]
            if appeal.status == "new":
                appeal.status = "in_progress"
            gathered.notes.append(
                f"EZO drafted the reply letter to {appeal.number} on the letterhead (Word card under the message). It is a DRAFT: the user checks it, signs and sends it, then says “{appeal.number} ga javob berildi”."
            )

    async def _minutes(self, ctx: GatherContext, gathered: Gathered, on: date) -> None:
        tools = ctx.tools
        data = await self._json(
            ctx,
            gathered,
            EXTRACT_MINUTES.format(today=on.isoformat()),
            ctx.turn.text,
            "extract_minutes",
        )
        if data is None:
            return
        tasks = [
            office.TaskInput(title=str(t.get("title") or ""), assignee=str(t.get("assignee") or ""), due_on=_date(t.get("due_on")))
            for t in (data.get("tasks") or []) if isinstance(t, dict) and str(t.get("title") or "").strip()
        ]  # fmt: skip
        meeting, created = await office.create_meeting(
            tools.session, tools.user_id, title=str(data.get("title") or "Yig‘ilish"),
            held_on=_date(data.get("held_on"), on) or on, notes=ctx.turn.text, tasks=tasks,
        )  # fmt: skip

        def items(key: str) -> list[str]:
            return [str(x) for x in (data.get(key) or []) if str(x).strip()]

        md = [f"# {meeting.title}", "", f"**Sana:** {meeting.held_on:%d.%m.%Y}"]
        if data.get("chair"):
            md.append(f"**Raislik qildi:** {data['chair']}")
        if items("attendees"):
            md.append("**Ishtirok etdi:** " + ", ".join(items("attendees")))
        for heading, key in (
            ("Kun tartibi", "agenda"),
            ("Muhokama", "discussion"),
            ("Qaror qilindi", "decisions"),
        ):
            if items(key):
                md += ["", f"## {heading}", "", *[f"{i}. {x}" for i, x in enumerate(items(key), 1)]]
        if created:
            md += [
                "",
                "## Topshiriqlar",
                "",
                "| № | Topshiriq | Mas’ul | Muddat |",
                "|---|---|---|---|",
            ]
            md += [
                f"| {t.number} | {t.title} | {t.assignee_name or '—'} | {t.due_on.strftime('%d.%m.%Y') if t.due_on else '—'} |"
                for t in created
            ]
        result = await call_tool(gathered, tools, "create_document", {
            "title": f"Bayonnoma — {meeting.title}"[:300], "markdown": "\n".join(md) + "\n", "format": "docx",
            "letterhead": True, "metadata": {"action": "meeting_minutes", "meeting_id": str(meeting.id)},
        })  # fmt: skip
        if result.ok:
            gathered.artifacts.append(result.data["artifact"])
            meeting.minutes_artifact_id = uuid.UUID(result.data["artifact"]["id"])
        unknown = [t.number for t in created if t.assignee_name and t.assignee_member_id is None]
        gathered.notes.append(
            f"EZO made the minutes of “{meeting.title}” ({meeting.held_on:%d.%m.%Y}) as a Word file on the letterhead and put {len(created)} task(s) into the register:\n- "
            + "\n- ".join(office.describe_task(t, on) for t in created)
            + (
                "\nThese handlers are not among the district's known people, so reminders cannot reach them yet: "
                + ", ".join(unknown)
                if unknown
                else ""
            )
            + "\nAsk the user to check the minutes; tasks can be marked done with “T-… bajarildi”."
        )

    async def _remind(self, ctx: GatherContext, gathered: Gathered, on: date) -> None:
        tools = ctx.tools
        db = tools.session
        settings = tools.services.settings
        sender = await district.sender_name(db, tools.user_id)
        items: list[tuple[uuid.UUID | None, str, str]] = []
        for appeal in await office.open_appeals(db, tools.user_id):
            if office.appeal_state(appeal, on) == "overdue":
                items.append(
                    (
                        appeal.assignee_member_id,
                        appeal.assignee_name,
                        f"{appeal.number} raqamli murojaat ({appeal.applicant}) bo‘yicha javob muddati {appeal.due_on:%d.%m.%Y} kuni o‘tgan. Iltimos, bugun javob bering",
                    )
                )
        for task in await office.open_tasks(db, tools.user_id):
            if office.task_state(task, on) == "overdue" and task.due_on:
                items.append(
                    (
                        task.assignee_member_id,
                        task.assignee_name,
                        f"{task.number} topshiriq («{task.title[:120]}») muddati {task.due_on:%d.%m.%Y} kuni o‘tgan. Iltimos, bajarilishini bugun ma’lum qiling",
                    )
                )
        if not items:
            gathered.notes.append("Nothing is overdue, so no warning was drafted. Say so.")
            return
        drafted, unreachable = 0, []
        for member_id, name, text in items[: district.MAX_DRAFTS_PER_TURN]:
            person = await db.get(DistrictMember, member_id) if member_id else None
            if person is None:
                unreachable.append(name or "belgilanmagan")
                continue
            notice = DistrictNotice(
                user_id=tools.user_id, project_id=None, member_id=person.id, recipient_name=person.full_name,
                text=f"Hurmatli {person.full_name}! {text}. — {sender}", channels=district.available_channels(settings, person),
                sender=sender, status="draft",
            )  # fmt: skip
            db.add(notice)
            await db.flush()
            gathered.notices.append(district.notice_out(notice))
            drafted += 1
        gathered.tool_calls.append(
            {"tool": "draft_reminders", "ok": True, "summary": f"{drafted} draft(s)", "error": None}
        )
        gathered.notes.append(
            f"EZO prepared {drafted} reminder DRAFT(S) for overdue appeals and tasks (NOT sent; the owner presses “Yuborish” on each card)."
            + (
                f" These handlers are not among the district's known people, so no draft was made: {', '.join(unreachable)}."
                if unreachable
                else ""
            )
        )

    async def _report(
        self, ctx: GatherContext, gathered: Gathered, on: date, *, monthly: bool
    ) -> None:
        tools = ctx.tools
        start = on - timedelta(days=30 if monthly else 7)
        district_lines = []
        for project in await district.projects(tools.session, tools.user_id):
            if project.status != "active":
                continue
            status = await district.status(tools.session, project, tools.services.settings)
            pct = f"{status.percent:g}%" if status.percent is not None else "—"
            district_lines.append(
                f"- **{project.name}**: {status.done:g} / {status.target:g} {project.unit} ({pct}); orqada: {len(status.behind)} kishi"
            )
        markdown, stats = await office.report_markdown(
            tools.session, tools.user_id, start=start, end=on, district_lines=district_lines
        )
        result = await call_tool(gathered, tools, "create_document", {
            "title": f"{'Oylik' if monthly else 'Haftalik'} hisobot — {on:%d.%m.%Y}", "markdown": markdown,
            "format": "docx", "artifact_type": "report", "letterhead": True, "metadata": {"action": "office_report", **stats},
        })  # fmt: skip
        if result.ok:
            gathered.artifacts.append(result.data["artifact"])
        gathered.notes.append(
            f"EZO made the {'monthly' if monthly else 'weekly'} report ({start:%d.%m.%Y}–{on:%d.%m.%Y}) as a Word file from the database: "
            + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in stats.items())
            + (
                ". District projects: "
                + "; ".join(line.lstrip("- ").replace("**", "") for line in district_lines)
                if district_lines
                else ""
            )
            + ". Summarise these numbers briefly."
        )

    async def _overview(self, ctx: GatherContext, gathered: Gathered, on: date) -> None:
        tools = ctx.tools
        appeals = await office.open_appeals(tools.session, tools.user_id)
        tasks = await office.open_tasks(tools.session, tools.user_id)
        if not appeals and not tasks:
            gathered.notes.append(
                "The devonxona register is empty. Explain in 3 lines what the user can say: “Yangi murojaat: …”, “Yig‘ilish bayonnomasini tuz: …”, “Haftalik hisobot tayyorla”."
            )
            return
        urgent_a = [a for a in appeals if office.appeal_state(a, on) in ("overdue", "due_soon")]
        urgent_t = [t for t in tasks if office.task_state(t, on) in ("overdue", "due_soon")]
        lines = [f"Open appeals: {len(appeals)}; open tasks: {len(tasks)}."]
        if urgent_a:
            lines += ["Appeals overdue or due within 3 days:"] + [
                f"- {office.describe_appeal(a, on)}" for a in urgent_a[:15]
            ]
        if urgent_t:
            lines += ["Tasks overdue or due within 3 days:"] + [
                f"- {office.describe_task(t, on)}" for t in urgent_t[:15]
            ]
        if not urgent_a and not urgent_t:
            lines.append("Nothing is overdue or due within 3 days.")
        gathered.notes.append("\n".join(lines))


__all__ = ["Appeal", "ChanceryAgent", "wants_chancery"]
