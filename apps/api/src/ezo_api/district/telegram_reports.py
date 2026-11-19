"""Employees report their progress to EZO's Telegram bot.

A responsible person whose Telegram is linked (JARVIS recipient, attached to them on the
Tuman markazi page) writes to the bot:

    "12"            → adds 12 to their done count (one project assigned)
    "xatlov 12"     → adds 12 to the project named "Xatlov …"
    "jami 45"       → sets the done count to 45 (also "=45", "hammasi 45")

EZO answers in the same chat with the new total. Messages from chats nobody linked are stored
for linking (/start codes) and otherwise ignored; EZO never answers strangers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DistrictAssignment,
    DistrictMember,
    DistrictProgress,
    DistrictProject,
    TelegramInboxMessage,
    TelegramRecipient,
)
from ezo_api.district.service import match_projects
from ezo_api.jarvis.telegram import TelegramClient, TelegramError, get_updates, send_text

logger = logging.getLogger(__name__)

KEEP = timedelta(days=7)
_NUMBER = re.compile(r"(?<![\w.])(\d{1,7}(?:[.,]\d{1,2})?)(?![\w.])")
_SET = re.compile(r"(^\s*=|\b(jami|hammasi|umumiy|итого|всего|total)\b)")

HELP = (
    "Hisobot yuborish uchun bajarilgan sonni yozing, masalan: «12» (bugun qo‘shildi) yoki "
    "«jami 45» (umumiy son). Bir nechta loyiha bo‘lsa, nomini ham yozing: «xatlov 12»."
)


@dataclass(frozen=True, slots=True)
class Report:
    value: float
    absolute: bool
    words: str


def parse_report(text: str) -> Report | None:
    norm = normalize(text)
    numbers = _NUMBER.findall(norm)
    if len(numbers) != 1:
        return None
    value = float(numbers[0].replace(",", "."))
    words = _NUMBER.sub(" ", norm)
    return Report(value=value, absolute=bool(_SET.search(norm)), words=" ".join(words.split()))


async def fetch(db: AsyncSession, client: TelegramClient) -> int:
    """Store new private messages; confirm everything read to Telegram. Returns the count."""
    last = await db.scalar(select(func.max(TelegramInboxMessage.update_id)))
    updates = await get_updates(client, last + 1 if last is not None else None)
    stored = 0
    for item in updates:
        if not item.chat_id or not item.text.strip():
            continue
        exists = await db.scalar(
            select(TelegramInboxMessage.id).where(TelegramInboxMessage.update_id == item.update_id)
        )
        if exists:
            continue
        db.add(
            TelegramInboxMessage(
                update_id=item.update_id,
                chat_id=item.chat_id,
                sender_name=item.name,
                text=item.text,
                received_at=datetime.fromtimestamp(item.date, UTC) if item.date else utcnow(),
            )
        )
        stored += 1
    if updates and not stored:
        # Non-text updates only: remember how far we read so they are not fetched again.
        db.add(
            TelegramInboxMessage(
                update_id=max(u.update_id for u in updates), chat_id="", text="",
                received_at=utcnow(), processed_at=utcnow(), outcome="skipped",
            )
        )  # fmt: skip
    await db.execute(
        delete(TelegramInboxMessage).where(TelegramInboxMessage.received_at < utcnow() - KEEP)
    )
    await db.flush()
    return stored


async def find_start(db: AsyncSession, code: str) -> TelegramInboxMessage | None:
    return await db.scalar(
        select(TelegramInboxMessage)
        .where(TelegramInboxMessage.text == f"/start {code}")
        .order_by(TelegramInboxMessage.received_at.desc())
        .limit(1)
    )


async def _apply(
    db: AsyncSession, member: DistrictMember, report: Report
) -> tuple[str, str] | None:
    """(project, reply) after applying the report, or None when no project matches."""
    rows = list(
        await db.execute(
            select(DistrictAssignment, DistrictProject)
            .join(DistrictProject, DistrictProject.id == DistrictAssignment.project_id)
            .where(DistrictAssignment.member_id == member.id, DistrictProject.status == "active")
        )
    )
    if not rows:
        return None
    projects = [p for _, p in rows]
    chosen = match_projects(report.words, projects) if report.words else []
    if len(chosen) != 1:
        if len(rows) != 1:
            names = ", ".join(f"«{p.name}»" for p in projects)
            return (
                "",
                f"Qaysi loyiha bo‘yicha? Loyiha nomini ham yozing ({names}), masalan: "
                f"«{projects[0].name.split()[0].lower()} 12».",
            )
        chosen = projects
    project = chosen[0]
    assignment = next(a for a, p in rows if p.id == project.id)
    new = report.value if report.absolute else assignment.done + report.value
    if new < 0 or (assignment.target and new > assignment.target * 3):
        return project.name, "Bu son rejadan juda katta ko‘rinadi; tekshirib qayta yozing."
    now = utcnow()
    assignment.done, assignment.source, assignment.reported_at = new, "telegram", now
    db.add(
        DistrictProgress(assignment_id=assignment.id, done=new, source="telegram", recorded_at=now)
    )
    pct = f" ({round(100 * new / assignment.target):g}%)" if assignment.target else ""
    return project.name, (
        f"✅ Qabul qilindi: «{project.name}» — {new:g} / {assignment.target:g} {project.unit}{pct}."
    )


async def process(db: AsyncSession, client: TelegramClient | None) -> int:
    """Handle unprocessed messages from linked responsible people. Returns how many."""
    pending = list(
        await db.scalars(
            select(TelegramInboxMessage)
            .where(TelegramInboxMessage.processed_at.is_(None))
            .order_by(TelegramInboxMessage.update_id)
            .limit(200)
        )
    )
    handled = 0
    for message in pending:
        if message.text.startswith("/"):
            message.processed_at, message.outcome = utcnow(), "command"
            continue
        members = list(
            await db.scalars(
                select(DistrictMember)
                .join(
                    TelegramRecipient, TelegramRecipient.id == DistrictMember.telegram_recipient_id
                )
                .where(
                    TelegramRecipient.chat_id == message.chat_id,
                    TelegramRecipient.status == "verified",
                )
            )
        )
        if not members:
            message.processed_at, message.outcome = utcnow(), "unknown_sender"
            continue
        report = parse_report(message.text)
        reply = HELP
        outcome = "help"
        if report is not None:
            for member in members:
                result = await _apply(db, member, report)
                if result is not None:
                    project, reply = result
                    outcome = "applied" if project and reply.startswith("✅") else "asked"
                    break
            else:
                reply = "Sizga hozircha faol loyiha biriktirilmagan."
                outcome = "no_project"
        message.processed_at, message.outcome = utcnow(), outcome
        handled += 1
        await db.flush()
        if client is not None:
            try:
                await send_text(client, message.chat_id, reply)
            except TelegramError as exc:
                logger.warning("Telegram reply failed: %s", exc.message)
    await db.flush()
    return handled


async def poll_once(db: AsyncSession, client: TelegramClient) -> tuple[int, int]:
    stored = await fetch(db, client)
    handled = await process(db, client)
    return stored, handled
