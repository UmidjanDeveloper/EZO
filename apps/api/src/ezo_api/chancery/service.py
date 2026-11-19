"""Devonxona operations: numbering, appeals, meetings, tasks, deadlines and the report.

Deadlines: an appeal is due `APPEAL_DAYS` calendar days after it was received unless the
user sets another date (the appeals law allows a longer term when extra study is needed; the
person handling it decides). "Overdue" and "due soon" are computed from today's date in the
district's time zone, never stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import tokenize
from ezo_api.db.models import Appeal, DistrictMember, GovTask, Meeting

APPEAL_DAYS = 15
DUE_SOON_DAYS = 3
CHANNEL_NAMES = {
    "virtual_reception": "Virtual qabulxona",
    "president_portal": "Prezident portali",
    "written": "Yozma ariza",
    "oral": "Og‘zaki (qabulda)",
    "phone": "Telefon",
    "other": "Boshqa",
}
APPEAL_STATUS_NAMES = {
    "new": "yangi",
    "in_progress": "ko‘rib chiqilmoqda",
    "answered": "javob berilgan",
    "closed": "yopilgan",
}


class ChanceryError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


async def next_number(
    db: AsyncSession,
    model: type[Appeal] | type[GovTask],
    user_id: uuid.UUID,
    prefix: str,
    year: int,
) -> str:
    """ "M-2026-0007": one more than the highest number this year (gaps stay gaps)."""
    pattern = f"{prefix}-{year}-%"
    highest = await db.scalar(
        select(func.max(model.number)).where(model.user_id == user_id, model.number.like(pattern))
    )
    last = int(str(highest).rsplit("-", 1)[1]) if highest else 0
    return f"{prefix}-{year}-{last + 1:04d}"


async def find_member(db: AsyncSession, user_id: uuid.UUID, name: str) -> DistrictMember | None:
    """A responsible person by surname (allowing case endings), when exactly one matches."""
    words = [w for w in tokenize(name) if len(w) >= 3]
    if not words:
        return None
    people = list(await db.scalars(select(DistrictMember).where(DistrictMember.user_id == user_id)))
    found = []
    for person in people:
        parts = [p for p in tokenize(person.full_name) if len(p) >= 3]
        if parts and any(w.startswith(parts[0][: max(4, len(parts[0]) - 1)]) for w in words):
            found.append(person)
    return found[0] if len(found) == 1 else None


# --- appeals ------------------------------------------------------------------------------


async def create_appeal(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    applicant: str,
    summary: str,
    received_on: date,
    contact: str = "",
    channel: str = "other",
    due_on: date | None = None,
    assignee: str = "",
) -> Appeal:
    if not applicant.strip() or not summary.strip():
        raise ChanceryError("missing", "An appeal needs the applicant and what it is about.")
    if channel not in CHANNEL_NAMES:
        channel = "other"
    member = await find_member(db, user_id, assignee) if assignee else None
    appeal = Appeal(
        user_id=user_id,
        number=await next_number(db, Appeal, user_id, "M", received_on.year),
        applicant=" ".join(applicant.split())[:200],
        contact=" ".join(contact.split())[:300],
        channel=channel,
        summary=summary.strip()[:5000],
        received_on=received_on,
        due_on=due_on or received_on + timedelta(days=APPEAL_DAYS),
        assignee_member_id=member.id if member else None,
        assignee_name=(member.full_name if member else " ".join(assignee.split()))[:160],
        status="new",
    )
    db.add(appeal)
    await db.flush()
    return appeal


async def appeal_by_number(db: AsyncSession, user_id: uuid.UUID, number: str) -> Appeal | None:
    return await db.scalar(
        select(Appeal).where(Appeal.user_id == user_id, Appeal.number == number.upper())
    )


async def open_appeals(db: AsyncSession, user_id: uuid.UUID) -> list[Appeal]:
    return list(
        await db.scalars(
            select(Appeal)
            .where(Appeal.user_id == user_id, Appeal.status.in_(("new", "in_progress")))
            .order_by(Appeal.due_on, Appeal.number)
        )
    )


def appeal_state(appeal: Appeal, on: date) -> str:
    if appeal.status in ("answered", "closed"):
        return appeal.status
    if appeal.due_on < on:
        return "overdue"
    if (appeal.due_on - on).days <= DUE_SOON_DAYS:
        return "due_soon"
    return appeal.status


def describe_appeal(appeal: Appeal, on: date) -> str:
    state = appeal_state(appeal, on)
    days = (appeal.due_on - on).days
    when = (
        f"OVERDUE by {-days} day(s)"
        if state == "overdue"
        else f"due {appeal.due_on.isoformat()} ({days} day(s) left)"
        if state in ("new", "in_progress", "due_soon")
        else f"{APPEAL_STATUS_NAMES.get(appeal.status, appeal.status)}"
        + (f" on {appeal.answered_on.isoformat()}" if appeal.answered_on else "")
    )
    who = f"; handled by {appeal.assignee_name}" if appeal.assignee_name else "; NO ONE ASSIGNED"
    return (
        f"{appeal.number} — {appeal.applicant} ({CHANNEL_NAMES[appeal.channel]}, received "
        f"{appeal.received_on.isoformat()}): {appeal.summary[:200]} — {when}{who}."
    )


# --- meetings and tasks --------------------------------------------------------------------


@dataclass(slots=True)
class TaskInput:
    title: str
    assignee: str = ""
    due_on: date | None = None


async def create_meeting(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    held_on: date,
    notes: str,
    tasks: list[TaskInput],
) -> tuple[Meeting, list[GovTask]]:
    meeting = Meeting(user_id=user_id, title=title.strip()[:300] or "Yig‘ilish", held_on=held_on,
                      notes=notes[:100_000])  # fmt: skip
    db.add(meeting)
    await db.flush()
    created = [await create_task(db, user_id, item, meeting_id=meeting.id) for item in tasks[:50]]
    return meeting, created


async def create_task(
    db: AsyncSession, user_id: uuid.UUID, item: TaskInput, *, meeting_id: uuid.UUID | None = None
) -> GovTask:
    if not item.title.strip():
        raise ChanceryError("missing", "A task needs a description.")
    member = await find_member(db, user_id, item.assignee) if item.assignee else None
    year = (item.due_on or datetime.now(UTC).date()).year
    task = GovTask(
        user_id=user_id,
        number=await next_number(db, GovTask, user_id, "T", year),
        meeting_id=meeting_id,
        title=item.title.strip()[:2000],
        assignee_member_id=member.id if member else None,
        assignee_name=(member.full_name if member else " ".join(item.assignee.split()))[:160],
        due_on=item.due_on,
        status="open",
    )
    db.add(task)
    await db.flush()
    return task


async def open_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[GovTask]:
    return list(
        await db.scalars(
            select(GovTask)
            .where(GovTask.user_id == user_id, GovTask.status == "open")
            .order_by(GovTask.due_on.is_(None), GovTask.due_on, GovTask.number)
        )
    )


def task_state(task: GovTask, on: date) -> str:
    if task.status != "open" or task.due_on is None:
        return task.status
    if task.due_on < on:
        return "overdue"
    if (task.due_on - on).days <= DUE_SOON_DAYS:
        return "due_soon"
    return "open"


def describe_task(task: GovTask, on: date) -> str:
    state = task_state(task, on)
    if task.due_on is None:
        when = "no deadline"
    elif state == "overdue":
        when = f"OVERDUE by {(on - task.due_on).days} day(s) (due {task.due_on.isoformat()})"
    else:
        when = f"due {task.due_on.isoformat()}"
    who = task.assignee_name or "NO ONE ASSIGNED"
    if task.status != "open":
        when = task.status + (f" on {task.done_on.isoformat()}" if task.done_on else "")
    return f"{task.number} — {task.title[:200]} — {who} — {when}."


# --- report ------------------------------------------------------------------------------


async def report_markdown(
    db: AsyncSession, user_id: uuid.UUID, *, start: date, end: date, district_lines: list[str]
) -> tuple[str, dict[str, Any]]:
    """The office report for a period: appeals, tasks and district projects (facts only)."""
    appeals = list(await db.scalars(select(Appeal).where(Appeal.user_id == user_id)))
    tasks = list(await db.scalars(select(GovTask).where(GovTask.user_id == user_id)))
    received = [a for a in appeals if start <= a.received_on <= end]
    answered = [a for a in appeals if a.answered_on and start <= a.answered_on <= end]
    late = [a for a in appeals if appeal_state(a, end) == "overdue"]
    given = [t for t in tasks if t.created_at and start <= t.created_at.date() <= end]
    done = [t for t in tasks if t.done_on and start <= t.done_on <= end]
    overdue_tasks = [t for t in tasks if task_state(t, end) == "overdue"]
    stats = {
        "appeals_received": len(received),
        "appeals_answered": len(answered),
        "appeals_overdue": len(late),
        "tasks_given": len(given),
        "tasks_done": len(done),
        "tasks_overdue": len(overdue_tasks),
    }
    lines = [
        f"# Hisobot: {start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}",
        "",
        "## Murojaatlar",
        "",
        f"- Kelib tushgan: {len(received)}",
        f"- Javob berilgan: {len(answered)}",
        f"- Muddati o‘tgan (javobsiz): {len(late)}",
    ]
    by_channel: dict[str, int] = {}
    for a in received:
        by_channel[a.channel] = by_channel.get(a.channel, 0) + 1
    for channel, count in sorted(by_channel.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {CHANNEL_NAMES[channel]}: {count}")
    if late:
        lines += ["", "**Muddati o‘tgan murojaatlar:**", ""]
        lines += [
            f"- {a.number} — {a.applicant}: {a.summary[:120]} (muddat {a.due_on:%d.%m.%Y}; "
            f"mas’ul: {a.assignee_name or 'belgilanmagan'})"
            for a in late[:30]
        ]
    lines += [
        "",
        "## Topshiriqlar",
        "",
        f"- Berilgan: {len(given)}",
        f"- Bajarilgan: {len(done)}",
        f"- Muddati o‘tgan: {len(overdue_tasks)}",
    ]
    if overdue_tasks:
        lines += ["", "**Muddati o‘tgan topshiriqlar:**", ""]
        lines += [
            f"- {t.number} — {t.title[:120]} (mas’ul: {t.assignee_name or 'belgilanmagan'}; "
            f"muddat {t.due_on:%d.%m.%Y})"
            for t in overdue_tasks[:30]
            if t.due_on
        ]
    if district_lines:
        lines += ["", "## Tuman loyihalari", "", *district_lines]
    lines += ["", f"*EZO bazasidagi ma’lumotlar asosida, {end:%d.%m.%Y} holatiga.*"]
    return "\n".join(lines) + "\n", stats
