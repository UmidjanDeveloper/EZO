"""Reading a schedule request from the owner's words (uz Latin/Cyrillic, en, ru).

"Har dushanba soat 9 da haftalik hisobot tayyorla"     → weekly_report, 1, 09:00
"Har kuni ertalab 8:30 da muddatlarni eslat"           → deadline_digest, every day, 08:30
"Har oyning 1-kuni oylik hisobot, telegramga yubor"    → monthly_report, day 1, Telegram
"Jadvalimni ko'rsat" / "Haftalik hisobotni to'xtat"    → list / stop
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ezo_api.core.text import normalize
from ezo_api.translation.translit import to_latin

_DAYS: tuple[tuple[int, str], ...] = (
    (1, r"dushanba|monday|понедельник"),
    (2, r"seshanba|tuesday|вторник"),
    (3, r"chorshanba|wednesday|сред[ау]"),
    (4, r"payshanba|thursday|четверг"),
    (5, r"juma|friday|пятниц"),
    (6, r"shanba|saturday|суббот"),
    (7, r"yakshanba|sunday|воскресень"),
)
RECURRING = re.compile(
    r"(\bhar\s+(kuni|kun|hafta|oy|dushanba|seshanba|chorshanba|payshanba|juma|shanba|yakshanba)"
    r"|\bish\s+kunlari|\bhar\s+oyning|\bevery\s+(day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday)"
    r"|\bкажд(ый|ую|ое)\b|\bпо\s+(понедельникам|вторникам|средам|четвергам|пятницам|будням))"
)
LIST = re.compile(
    r"(jadval(im|ingiz)?(ni)?\s+(ko'rsat|qanday|nima)|rejalashtirilgan\s+(ish|vazifa)|"
    r"(show|list)\s+(my\s+)?schedule|scheduled\s+jobs|моё?\s+расписание|покажи\s+расписание)"
)
STOP = re.compile(r"(to'xtat|o'chir|bekor\s+qil|stop|cancel|disable|отключи|останови|отмени)")
_KINDS: tuple[tuple[str, str], ...] = (
    (
        "monthly_report",
        r"oylik\s+hisobot|monthly\s+report|месячн\w*\s+отч[её]т|ежемесячн\w*\s+отч[её]т",
    ),
    ("weekly_report", r"haftalik\s+hisobot|hisobot|weekly\s+report|report|отч[её]т"),
    ("deadline_digest", r"muddat|kechik|eslat|deadline|overdue|remind|срок|просроч|напомин"),
    ("district_sync", r"tuman\s+loyiha|loyihalar|xatlov|district|проект"),
    ("lexuz_recheck", r"lex\.?uz|qonun|hujjatlarni\s+qayta|law|закон"),
)
TELEGRAM = re.compile(r"telegram|телеграм")


@dataclass(frozen=True, slots=True)
class ScheduleRequest:
    kind: str | None
    weekdays: str
    at_time: str
    month_day: int | None
    telegram: bool


def _text(text: str) -> str:
    return normalize(to_latin(text)) + " " + normalize(text)


def is_recurring(text: str) -> bool:
    return bool(RECURRING.search(_text(text)))


def wants_list(text: str) -> bool:
    return bool(LIST.search(_text(text)))


def wants_stop(text: str) -> bool:
    return bool(STOP.search(_text(text)))


def kind_of(text: str) -> str | None:
    norm = _text(text)
    for kind, pattern in _KINDS:
        if re.search(pattern, norm):
            return kind
    return None


def _time(norm: str) -> str:
    match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", norm)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    match = re.search(r"(soat|at|в)\s*([01]?\d|2[0-3])\b", norm) or re.search(
        r"\b([01]?\d|2[0-3])\s*(da|ga|часов|часа|am|pm)\b", norm
    )
    if match:
        hour = int(match.group(2) if match.group(1) in ("soat", "at", "в") else match.group(1))
        if "pm" in match.group(0) and hour < 12:
            hour += 12
        if re.search(r"(kechqurun|kechki|evening|вечер)", norm) and hour < 12:
            hour += 12
        return f"{hour:02d}:00"
    if re.search(r"(kechqurun|evening|вечер)", norm):
        return "18:00"
    return "09:00"


def parse(text: str) -> ScheduleRequest:
    norm = _text(text)
    month_day = None
    weekdays = ""
    match = re.search(
        r"oyning\s+(\d{1,2})|(\d{1,2})[- ]?(kuni|числа|of each month|of the month)", norm
    )
    if match or re.search(r"\bhar\s+oy|every\s+month|ежемесячн|каждый\s+месяц", norm):
        day = int((match.group(1) or match.group(2)) if match else 1)
        month_day = min(max(day, 1), 31)
    else:
        if re.search(r"ish\s+kunlari|weekday|будн", norm):
            weekdays = "1,2,3,4,5"
        else:
            days = [n for n, pattern in _DAYS if re.search(rf"(?<![a-z]){pattern}", norm)]
            # "yakshanba"/"seshanba"/"chorshanba"/"payshanba" also contain "shanba".
            if 6 in days and not re.search(r"(?<![a-z])shanba", norm):
                days.remove(6)
            weekdays = ",".join(str(d) for d in days)
            if not days and re.search(
                r"\bhar\s+hafta|every\s+week|еженедельн|каждую\s+неделю", norm
            ):
                weekdays = "1"
    kind = kind_of(text)
    if kind == "weekly_report" and month_day is not None:
        kind = "monthly_report"
    return ScheduleRequest(
        kind=kind,
        weekdays=weekdays,
        at_time=_time(norm),
        month_day=month_day,
        telegram=bool(TELEGRAM.search(norm)),
    )


def wants_schedule(text: str) -> bool:
    """A recurring job ("har dushanba … hisobot") or stopping one ("… jadvalni to'xtat")."""
    norm = _text(text)
    if kind_of(text) is not None and is_recurring(text):
        return True
    return bool(re.search(r"jadval", norm) and (wants_stop(text) or wants_list(text)))
