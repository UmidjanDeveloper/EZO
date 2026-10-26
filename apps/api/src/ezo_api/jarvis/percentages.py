"""Labelled percentages from two documents, compared with exact decimal arithmetic.

"Prepare the percentages like the previous file" is implemented literally and
transparently: EZO takes the previous file's labelled percentages (its structure and
order), finds the same labels in the newest file and reports each value and the change
in percentage points. Labels missing from either file are listed, never invented.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_ROWS = 200
# "Ishsizlik darajasi: 12,5%" / "Growth — 3.4 %" / "Доля рынка 41%"
_LINE = re.compile(
    r"^\s*(?P<label>[^\d%\n]{2,120}?)[\s:=–—-]*(?P<value>-?\d{1,4}(?:[.,]\d{1,6})?)\s?%",
    re.M,
)


@dataclass(frozen=True, slots=True)
class LabelledPercent:
    label: str
    key: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class PercentRow:
    label: str
    previous: Decimal | None
    current: Decimal | None

    @property
    def change_pp(self) -> Decimal | None:
        if self.previous is None or self.current is None:
            return None
        return self.current - self.previous


def _key(label: str) -> str:
    text = unicodedata.normalize("NFKC", label).casefold()
    return re.sub(r"[^\w]+", " ", text).strip()


def extract_percentages(text: str) -> list[LabelledPercent]:
    found: list[LabelledPercent] = []
    seen: set[str] = set()
    for match in _LINE.finditer(text):
        label = match.group("label").strip(" \t:=–—-.,;")
        key = _key(label)
        if not key or key in seen:
            continue
        try:
            value = Decimal(match.group("value").replace(",", "."))
        except InvalidOperation:
            continue
        seen.add(key)
        found.append(LabelledPercent(label, key, value))
        if len(found) >= MAX_ROWS:
            break
    return found


@dataclass(frozen=True, slots=True)
class Comparison:
    rows: list[PercentRow]
    only_in_current: list[LabelledPercent]

    @property
    def matched(self) -> int:
        return sum(1 for r in self.rows if r.change_pp is not None)


def compare(previous_text: str, current_text: str) -> Comparison:
    previous = extract_percentages(previous_text)
    current = {p.key: p for p in extract_percentages(current_text)}
    rows = [
        PercentRow(p.label, p.value, current.pop(p.key).value if p.key in current else None)
        for p in previous
    ]
    return Comparison(rows=rows, only_in_current=list(current.values()))


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return "—"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def report_markdown(comparison: Comparison, previous_name: str, current_name: str) -> str:
    """The report EZO renders to PDF. Every number comes from the two files."""
    lines = [
        f"Oldingi fayl: **{previous_name}** · Yangi fayl: **{current_name}**",
        "",
        "| Ko'rsatkich | Oldingi, % | Yangi, % | O'zgarish, p.p. |",
        "|---|---:|---:|---:|",
    ]
    for row in comparison.rows:
        change = row.change_pp
        sign = "+" if change is not None and change > 0 else ""
        lines.append(
            f"| {row.label} | {_fmt(row.previous)} | {_fmt(row.current)} | {sign}{_fmt(change)} |"
        )
    if comparison.only_in_current:
        lines += ["", "Faqat yangi faylda bor:", ""]
        lines += [f"- {p.label}: {_fmt(p.value)}%" for p in comparison.only_in_current]
    missing = [r.label for r in comparison.rows if r.current is None]
    if missing:
        lines += ["", "Yangi faylda topilmadi: " + ", ".join(missing)]
    lines += [
        "",
        "_EZO qiymatlarni fayllardan o'qib, aniq o'nlik arifmetika bilan hisobladi; "
        "model hech qanday raqam qo'shmagan._",
    ]
    return "\n".join(lines)
