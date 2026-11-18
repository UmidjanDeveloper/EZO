"""District center operations on the database (one owner account's data only)."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import tokenize
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DistrictAssignment,
    DistrictMember,
    DistrictNotice,
    DistrictProgress,
    DistrictProject,
    OrganizationProfile,
    TelegramRecipient,
)
from ezo_api.district.progress import ProjectStatus, compute
from ezo_api.district.records import Record, RecordsError, from_api
from ezo_api.district.sms import EskizClient, SmsError
from ezo_api.jarvis.telegram import TelegramClient, TelegramError, send_text
from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.settings import Settings

logger = logging.getLogger(__name__)

SYNC_EVERY = timedelta(minutes=10)
MAX_DRAFTS_PER_TURN = 20
TOKEN_ENV = re.compile(r"^EZO_DISTRICT_API_TOKEN(_[A-Z0-9]{1,30})?$")
AUTH_HEADER = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,40}$")
CHANNELS = ("telegram", "sms")


class DistrictError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


# --- projects and people --------------------------------------------------------------------


async def projects(db: AsyncSession, user_id: uuid.UUID) -> list[DistrictProject]:
    return list(
        await db.scalars(
            select(DistrictProject)
            .where(DistrictProject.user_id == user_id)
            .order_by(DistrictProject.created_at)
        )
    )


async def project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> DistrictProject:
    found = await db.get(DistrictProject, project_id)
    if found is None or found.user_id != user_id:
        raise DistrictError("not_found", "Project not found.", 404)
    return found


async def member(db: AsyncSession, user_id: uuid.UUID, member_id: uuid.UUID) -> DistrictMember:
    found = await db.get(DistrictMember, member_id)
    if found is None or found.user_id != user_id:
        raise DistrictError("not_found", "Person not found.", 404)
    return found


async def assignments(
    db: AsyncSession, project_row: DistrictProject
) -> list[tuple[DistrictAssignment, DistrictMember]]:
    rows = await db.execute(
        select(DistrictAssignment, DistrictMember)
        .join(DistrictMember, DistrictMember.id == DistrictAssignment.member_id)
        .where(DistrictAssignment.project_id == project_row.id)
        .order_by(DistrictMember.full_name)
    )
    return [(a, m) for a, m in rows.all()]


def check_source(source: dict[str, Any]) -> dict[str, Any]:
    """An API source as stored: https URL, the NAME of an EZO_DISTRICT_API_TOKEN* variable
    (never its value), an optional header name, the list path and the field mapping."""
    url = str(source.get("url") or "").strip()
    if not url.startswith("https://") and not url.startswith("http://localhost"):
        raise DistrictError("bad_source", "The API address must start with https://.")
    token_env = str(source.get("token_env") or "").strip()
    if token_env and not TOKEN_ENV.match(token_env):
        raise DistrictError(
            "bad_source",
            "The token must come from a server variable named EZO_DISTRICT_API_TOKEN or "
            "EZO_DISTRICT_API_TOKEN_<NAME> (the value stays in .env).",
        )
    header = str(source.get("auth_header") or "Authorization").strip()
    if not AUTH_HEADER.match(header):
        raise DistrictError("bad_source", "Invalid header name.")
    fields = source.get("fields") or {}
    if not isinstance(fields, dict) or not str(fields.get("name") or "").strip():
        raise DistrictError("bad_source", "Map at least the “name” field of the API records.")
    allowed = ("name", "target", "done", "phone", "area", "position", "external_id")
    return {
        "url": url[:500],
        "token_env": token_env,
        "auth_header": header,
        "auth_prefix": str(source.get("auth_prefix") if "auth_prefix" in source else "Bearer")[:20],
        "items_path": str(source.get("items_path") or "")[:120],
        "fields": {k: str(v)[:120] for k, v in fields.items() if k in allowed and v},
    }


async def find_member(
    db: AsyncSession, user_id: uuid.UUID, record: Record
) -> DistrictMember | None:
    query = select(DistrictMember).where(DistrictMember.user_id == user_id)
    if record.external_id:
        found = await db.scalar(query.where(DistrictMember.external_id == record.external_id))
        if found:
            return found
    if record.phone:
        found = await db.scalar(query.where(DistrictMember.phone == record.phone))
        if found:
            return found
    for candidate in await db.scalars(query.where(DistrictMember.full_name == record.name)):
        return candidate
    return None


@dataclass(slots=True)
class ApplyResult:
    created_people: int = 0
    updated: int = 0
    unchanged: int = 0


async def apply_records(
    db: AsyncSession, project_row: DistrictProject, records: list[Record], source: str
) -> ApplyResult:
    """Upsert people and their plan/done for this project; each change gets a history row."""
    result = ApplyResult()
    now = utcnow()
    existing = {a.member_id: a for a, _ in await assignments(db, project_row)}
    for record in records:
        person = await find_member(db, project_row.user_id, record)
        if person is None:
            person = DistrictMember(
                user_id=project_row.user_id,
                full_name=record.name,
                phone=record.phone,
                area=record.area,
                position=record.position,
                external_id=record.external_id,
            )
            db.add(person)
            await db.flush()
            result.created_people += 1
        else:
            person.phone = record.phone or person.phone
            person.area = record.area or person.area
            person.position = record.position or person.position
            person.external_id = record.external_id or person.external_id
        assignment = existing.get(person.id)
        if assignment is None:
            assignment = DistrictAssignment(project_id=project_row.id, member_id=person.id)
            db.add(assignment)
            existing[person.id] = assignment
        changed = False
        if record.target is not None and record.target != assignment.target:
            assignment.target = record.target
            changed = True
        if record.done is not None and record.done != assignment.done:
            assignment.done = record.done
            changed = True
            await db.flush()
            db.add(
                DistrictProgress(
                    assignment_id=assignment.id, done=record.done, source=source, recorded_at=now
                )
            )
        if changed:
            assignment.source = source
            assignment.reported_at = now
            result.updated += 1
        else:
            result.unchanged += 1
    await db.flush()
    return result


async def sync(
    db: AsyncSession,
    project_row: DistrictProject,
    settings: Settings,
    fetcher: SafeFetcher,
    *,
    force: bool = False,
) -> ApplyResult | None:
    """Read the project's official API (at most every 10 minutes unless forced)."""
    if project_row.source_kind != "api":
        return None
    if (
        not force
        and project_row.last_sync_at is not None
        and utcnow() - project_row.last_sync_at < SYNC_EVERY
    ):
        return None
    source = project_row.source or {}
    headers = {"Accept": "application/json"}
    token_env = source.get("token_env") or ""
    if token_env:
        if token_env == "EZO_DISTRICT_API_TOKEN":  # noqa: S105 - a variable name, not a value
            secret = (
                settings.district_api_token.get_secret_value()
                if settings.district_api_token
                else ""
            )
        else:
            secret = os.environ.get(token_env, "")
        if not secret:
            project_row.last_sync_error = f"{token_env} is not set in .env."
            project_row.last_sync_at = utcnow()
            return None
        prefix = source.get("auth_prefix", "Bearer")
        headers[source.get("auth_header") or "Authorization"] = f"{prefix} {secret}".strip()
    try:
        page = await fetcher.fetch_json(str(source.get("url")), headers=headers)
        body = json.loads(page.data.decode("utf-8"))
        records = from_api(body, str(source.get("items_path") or ""), source.get("fields") or {})
    except FetchError as exc:
        project_row.last_sync_error = exc.message
        project_row.last_sync_at = utcnow()
        return None
    except (RecordsError, ValueError) as exc:
        project_row.last_sync_error = (
            getattr(exc, "message", None) or "The API answer is not valid JSON."
        )
        project_row.last_sync_at = utcnow()
        return None
    applied = await apply_records(db, project_row, records, "api")
    project_row.last_sync_at = utcnow()
    project_row.last_sync_error = None
    return applied


async def status(
    db: AsyncSession, project_row: DistrictProject, settings: Settings
) -> ProjectStatus:
    rows = [
        (str(m.id), m.full_name, m.area, a.target, a.done)
        for a, m in await assignments(db, project_row)
    ]
    return compute(
        name=project_row.name,
        unit=project_row.unit,
        start=project_row.start_date,
        deadline=project_row.deadline,
        today=today(settings),
        rows=rows,
    )


# --- chat matching ---------------------------------------------------------------------------

_STOP = frozenset(
    "loyiha loyihasi loyihani tuman tumani tumandagi bo'yicha qalay qanday ketyapti holati "
    "holat nima 2024 2025 2026 2027 the project of va bilan uchun".split()
)


def _stems(text: str) -> set[str]:
    return {t[:5] for t in tokenize(text) if len(t) >= 4 and t not in _STOP}


def match_projects(text: str, rows: list[DistrictProject]) -> list[DistrictProject]:
    """Projects whose name or alias words (first five letters) appear in the message."""
    said = _stems(text)
    found = []
    for row in rows:
        names = [row.name, *(row.aliases or [])]
        if any(_stems(n) and _stems(n) <= said for n in names) or any(
            _stems(n) & said for n in names
        ):
            found.append(row)
    return found


def match_people(text: str, people: list[DistrictMember]) -> list[DistrictMember]:
    """People whose surname (or first name and surname) appears in the message, allowing
    Uzbek case endings ("Aliyevni", "Aliyevga")."""
    words = [w for w in tokenize(text) if len(w) >= 3]
    found = []
    for person in people:
        parts = [p for p in tokenize(person.full_name) if len(p) >= 3]
        if not parts:
            continue
        surname = parts[0]
        stem = surname[: max(4, len(surname) - 1)]
        if any(w.startswith(stem) for w in words):
            found.append(person)
    return found


# --- notices ---------------------------------------------------------------------------------


async def sender_name(db: AsyncSession, user_id: uuid.UUID) -> str:
    profile = await db.scalar(
        select(OrganizationProfile)
        .where(OrganizationProfile.user_id == user_id)
        .order_by(OrganizationProfile.is_default.desc(), OrganizationProfile.created_at)
        .limit(1)
    )
    if profile is not None:
        if profile.head_position:
            return profile.head_position[:160]
        if profile.name:
            return profile.name[:160]
    return "Tuman hokimligi"


def notice_text(
    *,
    name: str,
    project_name: str,
    unit: str,
    target: float,
    done: float,
    sender: str,
    extra: str = "",
) -> str:
    pct = f" ({round(100 * done / target):g}%)" if target > 0 else ""
    text = (
        f"Hurmatli {name}! «{project_name}» bo‘yicha rejangiz {target:g} {unit}, "
        f"bajarilgani {done:g}{pct}. Iltimos, ishni tezlashtiring va natijani bugun ma’lum qiling."
    )
    if extra:
        text += " " + " ".join(extra.split())[:300]
    return f"{text} — {sender}"


def available_channels(settings: Settings, person: DistrictMember) -> list[str]:
    out = []
    if settings.telegram_bot_token and person.telegram_recipient_id:
        out.append("telegram")
    if settings.eskiz_email and settings.eskiz_password and person.phone:
        out.append("sms")
    return out


async def draft(
    db: AsyncSession,
    settings: Settings,
    project_row: DistrictProject,
    person: DistrictMember,
    assignment: DistrictAssignment | None,
    *,
    extra: str = "",
) -> DistrictNotice:
    sender = await sender_name(db, project_row.user_id)
    notice = DistrictNotice(
        user_id=project_row.user_id,
        project_id=project_row.id,
        member_id=person.id,
        recipient_name=person.full_name,
        text=notice_text(
            name=person.full_name,
            project_name=project_row.name,
            unit=project_row.unit,
            target=assignment.target if assignment else 0.0,
            done=assignment.done if assignment else 0.0,
            sender=sender,
            extra=extra,
        ),
        channels=available_channels(settings, person),
        sender=sender,
        status="draft",
    )
    db.add(notice)
    await db.flush()
    return notice


async def send(
    db: AsyncSession,
    settings: Settings,
    notice: DistrictNotice,
    approver: uuid.UUID,
    *,
    text: str | None = None,
    telegram: TelegramClient | None = None,
    sms: EskizClient | None = None,
) -> DistrictNotice:
    """Send an approved draft on every available channel; record each real result."""
    if notice.status != "draft":
        raise DistrictError("already_handled", f"This warning is already {notice.status}.", 409)
    if text is not None:
        cleaned = " ".join(text.split())
        if not 10 <= len(cleaned) <= 900:
            raise DistrictError("bad_text", "The message must be 10–900 characters.")
        notice.text = cleaned
    person = await db.get(DistrictMember, notice.member_id) if notice.member_id else None
    if person is None:
        raise DistrictError("no_recipient", "The person was deleted.", 409)
    channels = available_channels(settings, person)
    if not channels:
        raise DistrictError(
            "no_channel",
            "No way to reach this person: link their Telegram or add a phone number, and set "
            "EZO_TELEGRAM_BOT_TOKEN or EZO_ESKIZ_EMAIL/EZO_ESKIZ_PASSWORD in .env.",
            409,
        )
    notice.channels = channels
    notice.approved_by = approver
    notice.approved_at = utcnow()
    notice.attempts += 1
    results: dict[str, Any] = {}
    if "telegram" in channels:
        recipient = await db.get(TelegramRecipient, person.telegram_recipient_id)
        if recipient is None or recipient.status != "verified" or not recipient.chat_id:
            results["telegram"] = {"ok": False, "error": "Telegram is not linked (verified)."}
        else:
            assert settings.telegram_bot_token is not None
            client = telegram or TelegramClient(settings.telegram_bot_token.get_secret_value())
            try:
                receipt = await send_text(client, recipient.chat_id, notice.text)
                results["telegram"] = {"ok": True, "id": receipt.message_id}
            except TelegramError as exc:
                results["telegram"] = {
                    "ok": False,
                    "error": exc.message,
                    "unknown": exc.outcome_unknown,
                }
    if "sms" in channels:
        assert settings.eskiz_email and settings.eskiz_password and person.phone
        client_sms = sms or EskizClient(
            settings.eskiz_email, settings.eskiz_password.get_secret_value(), settings.eskiz_sender
        )
        try:
            sms_receipt = await client_sms.send(person.phone, notice.text)
            results["sms"] = {
                "ok": True,
                "id": sms_receipt.message_id,
                "status": sms_receipt.status,
            }
        except SmsError as exc:
            results["sms"] = {"ok": False, "error": exc.message, "unknown": exc.outcome_unknown}
    notice.results = results
    oks = [r["ok"] for r in results.values()]
    notice.status = "sent" if all(oks) else "partly_sent" if any(oks) else "failed"
    await db.flush()
    return notice


def notice_out(notice: DistrictNotice) -> dict[str, Any]:
    return {
        "id": str(notice.id),
        "project_id": str(notice.project_id) if notice.project_id else None,
        "member_id": str(notice.member_id) if notice.member_id else None,
        "recipient_name": notice.recipient_name,
        "text": notice.text,
        "channels": notice.channels,
        "status": notice.status,
        "sender": notice.sender,
        "approved_at": notice.approved_at.astimezone(UTC).isoformat()
        if notice.approved_at
        else None,
        "results": notice.results,
        "created_at": notice.created_at.astimezone(UTC).isoformat() if notice.created_at else None,
    }
