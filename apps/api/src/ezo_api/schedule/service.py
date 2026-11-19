# ruff: noqa: E501  (user-facing Uzbek text kept on one line)
"""Jadval: create jobs, run what is due (claimed with a lease, so two API processes never run
one job twice), keep each run's result and deliver it to the owner.

What a job does is fixed per kind; none of them messages other people.
- weekly_report / monthly_report — the Devonxona report (Word file) from the database
- deadline_digest — appeals and tasks that are overdue or due within 3 days
- district_sync — read every district project that has an official API, then the totals
- lexuz_recheck — re-read the hokimiyat set of laws on LEX.UZ (in the background)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import ScheduledJob, ScheduledRun, TelegramRecipient
from ezo_api.schedule.timing import describe, next_run

logger = logging.getLogger(__name__)

LEASE = timedelta(minutes=15)
KIND_TITLES = {
    "weekly_report": "Haftalik hisobot",
    "monthly_report": "Oylik hisobot",
    "deadline_digest": "Muddatlar bo‘yicha eslatma",
    "district_sync": "Tuman loyihalarini yangilash",
    "lexuz_recheck": "LEX.UZ hujjatlarini qayta tekshirish",
}


class ScheduleError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(slots=True)
class Outcome:
    summary: str
    artifact_id: uuid.UUID | None = None


def when(job: ScheduledJob) -> str:
    return describe(job.weekdays, job.at_time, job.month_day)


async def create_job(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    timezone: str,
    weekdays: str = "",
    at_time: str = "09:00",
    month_day: int | None = None,
    title: str | None = None,
    notify_recipient_id: uuid.UUID | None = None,
) -> ScheduledJob:
    if kind not in KIND_TITLES:
        raise ScheduleError("bad_kind", "Unknown job kind.")
    if notify_recipient_id is not None:
        recipient = await db.get(TelegramRecipient, notify_recipient_id)
        if recipient is None or recipient.user_id != user_id or recipient.status != "verified":
            raise ScheduleError("recipient_not_linked", "That Telegram chat is not linked.")
    existing = await db.scalar(
        select(ScheduledJob).where(
            ScheduledJob.user_id == user_id,
            ScheduledJob.kind == kind,
            ScheduledJob.weekdays == weekdays,
            ScheduledJob.at_time == at_time,
            ScheduledJob.month_day.is_(None)
            if month_day is None
            else ScheduledJob.month_day == month_day,
        )
    )
    if existing is not None:
        existing.enabled = True
        existing.next_run_at = next_run(
            weekdays=weekdays,
            at_time=at_time,
            month_day=month_day,
            timezone=timezone,
            after=utcnow(),
        )
        if notify_recipient_id is not None:
            existing.notify_recipient_id = notify_recipient_id
        await db.flush()
        return existing
    job = ScheduledJob(
        user_id=user_id,
        kind=kind,
        title=(title or KIND_TITLES[kind])[:160],
        weekdays=weekdays,
        at_time=at_time,
        month_day=month_day,
        notify_recipient_id=notify_recipient_id,
        params={},
        next_run_at=next_run(
            weekdays=weekdays,
            at_time=at_time,
            month_day=month_day,
            timezone=timezone,
            after=utcnow(),
        ),
    )
    db.add(job)
    await db.flush()
    return job


async def jobs_for(db: AsyncSession, user_id: uuid.UUID) -> list[ScheduledJob]:
    return list(
        await db.scalars(
            select(ScheduledJob)
            .where(ScheduledJob.user_id == user_id)
            .order_by(ScheduledJob.next_run_at)
        )
    )


async def claim_due(db: AsyncSession, now: datetime, limit: int = 5) -> list[uuid.UUID]:
    """Take up to `limit` due jobs; a job is taken only if nobody holds a live lease on it."""
    ids = list(
        await db.scalars(
            select(ScheduledJob.id)
            .where(
                ScheduledJob.enabled.is_(True),
                ScheduledJob.next_run_at <= now,
                or_(ScheduledJob.locked_until.is_(None), ScheduledJob.locked_until < now),
            )
            .order_by(ScheduledJob.next_run_at)
            .limit(limit)
        )
    )
    claimed: list[uuid.UUID] = []
    for job_id in ids:
        result = await db.execute(
            update(ScheduledJob)
            .where(
                ScheduledJob.id == job_id,
                or_(ScheduledJob.locked_until.is_(None), ScheduledJob.locked_until < now),
            )
            .values(locked_until=now + LEASE)
        )
        if result.rowcount == 1:  # type: ignore[attr-defined]
            claimed.append(job_id)
    await db.commit()
    return claimed


async def _report(db: AsyncSession, services: Any, job: ScheduledJob, monthly: bool) -> Outcome:
    from ezo_api.chancery import service as office
    from ezo_api.district import service as district
    from ezo_api.tools.base import ToolContext

    on = office.today(services.settings.timezone)
    start = on - timedelta(days=30 if monthly else 7)
    lines = []
    for project in await district.projects(db, job.user_id):
        if project.status != "active":
            continue
        status = await district.status(db, project, services.settings)
        pct = f"{status.percent:g}%" if status.percent is not None else "—"
        lines.append(
            f"- **{project.name}**: {status.done:g} / {status.target:g} {project.unit} ({pct}); orqada: {len(status.behind)} kishi"
        )
    markdown, stats = await office.report_markdown(
        db, job.user_id, start=start, end=on, district_lines=lines
    )
    ctx = ToolContext(session=db, services=services, user_id=job.user_id)
    result = await services.tools.execute(
        "create_document",
        {
            "title": f"{'Oylik' if monthly else 'Haftalik'} hisobot — {on:%d.%m.%Y}",
            "markdown": markdown,
            "format": "docx",
            "artifact_type": "report",
            "letterhead": True,
            "metadata": {"action": "office_report", "scheduled": True, **stats},
        },
        ctx,
    )
    numbers = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in stats.items())
    artifact_id = None
    if result.ok:
        artifact_id = uuid.UUID(str(result.data["artifact"]["id"]))
    summary = (
        f"{'Oylik' if monthly else 'Haftalik'} hisobot ({start:%d.%m.%Y}–{on:%d.%m.%Y}): {numbers}."
        + ("" if result.ok else f" Word faylni yaratib bo‘lmadi: {result.error}")
    )
    return Outcome(summary, artifact_id)


async def _digest(db: AsyncSession, services: Any, job: ScheduledJob) -> Outcome:
    from ezo_api.chancery import service as office

    on = office.today(services.settings.timezone)
    soon = on + timedelta(days=3)
    lines: list[str] = []
    for appeal in await office.open_appeals(db, job.user_id):
        state = office.appeal_state(appeal, on)
        if state == "overdue" or appeal.due_on <= soon:
            mark = "MUDDATI O‘TGAN" if state == "overdue" else f"muddat {appeal.due_on:%d.%m}"
            lines.append(
                f"• {appeal.number} — {appeal.applicant} ({mark}; {appeal.assignee_name or 'ijrochi yo‘q'})"
            )
    for task in await office.open_tasks(db, job.user_id):
        state = office.task_state(task, on)
        if task.due_on is not None and (state == "overdue" or task.due_on <= soon):
            mark = "MUDDATI O‘TGAN" if state == "overdue" else f"muddat {task.due_on:%d.%m}"
            lines.append(
                f"• {task.number} — {task.title[:80]} ({mark}; {task.assignee_name or 'ijrochi yo‘q'})"
            )
    if not lines:
        return Outcome(
            f"{on:%d.%m.%Y}: muddati o‘tgan yoki 3 kun ichida tugaydigan murojaat va topshiriq yo‘q."
        )
    return Outcome(f"{on:%d.%m.%Y} holatiga muddatlar ({len(lines)} ta):\n" + "\n".join(lines))


async def _district_sync(db: AsyncSession, services: Any, job: ScheduledJob) -> Outcome:
    from ezo_api.district import service as district

    lines: list[str] = []
    for project in await district.projects(db, job.user_id):
        if project.status != "active":
            continue
        note = ""
        if project.source_kind == "api":
            try:
                applied = await district.sync(
                    db, project, services.settings, services.fetcher, force=True
                )
                if applied is not None:
                    note = f" (API: {applied.updated} yangilandi)"
            except district.DistrictError as exc:
                note = f" (API o‘qilmadi: {exc.message})"
        status = await district.status(db, project, services.settings)
        pct = f"{status.percent:g}%" if status.percent is not None else "—"
        lines.append(
            f"• {project.name}: {status.done:g} / {status.target:g} {project.unit} ({pct}), orqada {len(status.behind)} kishi{note}"
        )
    if not lines:
        return Outcome("Faol tuman loyihasi yo‘q.")
    return Outcome("Tuman loyihalari:\n" + "\n".join(lines))


async def _lexuz(db: AsyncSession, services: Any, job: ScheduledJob) -> Outcome:
    from ezo_api.official.collections import COLLECTIONS

    collection = COLLECTIONS["hokimiyat"]
    run_id = await services.official.start_detached(
        services.db.sessionmaker,
        job.user_id,
        collection.connector,
        [i.source_doc_id for i in collection.items],
        collection.language,
    )
    return Outcome(
        f"LEX.UZ: «{collection.names['uz']}» to‘plamidagi {len(collection.items)} ta hujjat qayta o‘qilmoqda (sinxronlash {str(run_id)[:8]}). O‘zgarishlar «Rasmiy manbalar» bo‘limida ko‘rinadi."
    )


async def execute(db: AsyncSession, services: Any, job: ScheduledJob) -> Outcome:
    if job.kind in ("weekly_report", "monthly_report"):
        return await _report(db, services, job, monthly=job.kind == "monthly_report")
    if job.kind == "deadline_digest":
        return await _digest(db, services, job)
    if job.kind == "district_sync":
        return await _district_sync(db, services, job)
    return await _lexuz(db, services, job)


async def _notify(db: AsyncSession, services: Any, job: ScheduledJob, text: str) -> bool:
    if job.notify_recipient_id is None or services.settings.telegram_bot_token is None:
        return False
    recipient = await db.get(TelegramRecipient, job.notify_recipient_id)
    if recipient is None or recipient.status != "verified" or not recipient.chat_id:
        return False
    from ezo_api.jarvis.telegram import TelegramClient, TelegramError, send_text

    client = getattr(services, "district_telegram", None) or TelegramClient(
        services.settings.telegram_bot_token.get_secret_value()
    )
    try:
        await send_text(client, recipient.chat_id, f"EZO — {job.title}\n\n{text}")
    except TelegramError as exc:
        logger.warning("Scheduled job %s: Telegram delivery failed: %s", job.id, exc.message)
        return False
    return True


async def run_job(services: Any, job_id: uuid.UUID, *, manual: bool = False) -> ScheduledRun | None:
    """Run one claimed (or manually started) job and move it to its next time."""
    async with services.db.sessionmaker() as db:
        job = await db.get(ScheduledJob, job_id)
        if job is None:
            return None
        run = ScheduledRun(
            job_id=job.id, user_id=job.user_id, started_at=utcnow(), status="running"
        )
        db.add(run)
        await db.commit()
        try:
            outcome = await execute(db, services, job)
            run.status, run.summary, run.artifact_id = (
                "completed",
                outcome.summary,
                outcome.artifact_id,
            )
        except Exception as exc:  # one job's failure never stops the scheduler
            logger.exception("Scheduled job %s failed", job.id)
            await db.rollback()
            job = await db.get(ScheduledJob, job_id)
            run = await db.get(ScheduledRun, run.id)
            assert job is not None and run is not None
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        run.finished_at = utcnow()
        if run.status == "completed":
            run.notified = await _notify(db, services, job, run.summary)
        job.last_run_at, job.last_status, job.locked_until = run.finished_at, run.status, None
        if not manual:
            job.next_run_at = next_run(
                weekdays=job.weekdays, at_time=job.at_time, month_day=job.month_day,
                timezone=services.settings.timezone, after=max(utcnow(), job.next_run_at),
            )  # fmt: skip
        await db.commit()
        await db.refresh(run)
        return run


async def tick(services: Any) -> int:
    """Run every job that is due now. Missed times while EZO was off run once, not N times."""
    async with services.db.sessionmaker() as db:
        due = await claim_due(db, utcnow())
    for job_id in due:
        await run_job(services, job_id)
    return len(due)
