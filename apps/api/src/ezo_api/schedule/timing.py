"""When a job runs next: weekdays + HH:MM (or a day of the month) in the local time zone."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAY_NAMES = {
    1: "dushanba", 2: "seshanba", 3: "chorshanba", 4: "payshanba",
    5: "juma", 6: "shanba", 7: "yakshanba",
}  # fmt: skip


def parse_weekdays(value: str) -> list[int]:
    return sorted({int(p) for p in value.split(",") if p.strip().isdigit() and 1 <= int(p) <= 7})


def parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def next_run(
    *,
    weekdays: str,
    at_time: str,
    month_day: int | None,
    timezone: str,
    after: datetime,
) -> datetime:
    """The first moment strictly after `after` (UTC) that matches the schedule (UTC)."""
    zone = ZoneInfo(timezone)
    local = after.astimezone(zone)
    at = parse_time(at_time)
    days = parse_weekdays(weekdays)
    for offset in range(0, 400):
        day: date = local.date() + timedelta(days=offset)
        if month_day is not None:
            last = calendar.monthrange(day.year, day.month)[1]
            if day.day != min(month_day, last):
                continue
        elif days and day.isoweekday() not in days:
            continue
        candidate = datetime.combine(day, at, tzinfo=zone)
        if candidate > local:
            return candidate.astimezone(UTC)
    raise ValueError("No matching day for this schedule")


def describe(weekdays: str, at_time: str, month_day: int | None) -> str:
    """Uzbek, e.g. "har dushanba 09:00", "har kuni 08:30", "har oyning 1-kuni 09:00"."""
    if month_day is not None:
        return f"har oyning {month_day}-kuni {at_time}"
    days = parse_weekdays(weekdays)
    if not days or len(days) == 7:
        return f"har kuni {at_time}"
    if days == [1, 2, 3, 4, 5]:
        return f"ish kunlari {at_time}"
    return "har " + ", ".join(WEEKDAY_NAMES[d] for d in days) + f" {at_time}"
