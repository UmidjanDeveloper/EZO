# ruff: noqa: E501  (warning texts are kept on readable lines)
"""Checks of a translation against its source, without a model.

What is checked (every finding is a warning for the user, nothing is changed):
- numbers: the same numbers in both texts (thousand separators and decimal commas are
  normalised; a month name next to a number counts as that month's number, so
  "12-mart" and "March 12" agree);
- links and e-mail addresses unchanged;
- person names (surnames with -ov/-ev/-ova/-yeva/-ovich/-skiy…) still present, in any
  script or common romanisation;
- the user's glossary terms used;
- paragraphs: none empty, none left untranslated, no suspicious length change;
- the target script for Uzbek (Latin or Cyrillic);
- ambiguity notes from the translator and "[?]" marks.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ezo_api.core.text import normalize
from ezo_api.translation.glossary import Term, missing_in, relevant
from ezo_api.translation.languages import base, detect
from ezo_api.translation.translit import detect_script, to_latin

_THOUSANDS = re.compile(r"(?<=\d)[   ,.](?=\d{3}(?!\d))")
_DIGITS = re.compile(r"\d+")
_LINKS = re.compile(r"(?:https?://|www\.)[^\s<>\")\]]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MONTHS: dict[int, tuple[str, ...]] = {
    1: ("yanvar", "январ", "january", "jan"),
    2: ("fevral", "феврал", "february", "feb"),
    3: ("mart", "март", "march", "mar"),
    4: ("aprel", "апрел", "april", "apr"),
    5: ("may", "май", "мая", "мае"),
    6: ("iyun", "июн", "june", "jun"),
    7: ("iyul", "июл", "july", "jul"),
    8: ("avgust", "август", "august", "aug"),
    9: ("sentabr", "сентябр", "september", "sep"),
    10: ("oktabr", "октябр", "october", "oct"),
    11: ("noyabr", "ноябр", "november", "nov"),
    12: ("dekabr", "декабр", "december", "dec"),
}
_MONTH_WORD = re.compile(r"[a-zа-яё']+|\d+")
_NOT_MONTHS = {"marta", "marotaba"}  # "3 marta" is "three times" in Uzbek
_SURNAME = re.compile(
    r"\b([A-Z][a-z']{1,20}?(?:ovich|evich|yevich|ovna|evna|yevna|ova|eva|yeva|ov|ev|yev|skaya|skiy|sky))"
    r"(?=[a-z']{0,6}\b)"
)


def numbers(text: str) -> Counter[int]:
    """Numbers as values (separators normalised), plus month names next to a number."""
    joined = _THOUSANDS.sub("", text)
    values: Counter[int] = Counter(int(d) for d in _DIGITS.findall(joined) if len(d) < 16)
    tokens = _MONTH_WORD.findall(normalize(joined))
    for i, token in enumerate(tokens):
        if token.isdigit() or token in _NOT_MONTHS:
            continue
        near = (i > 0 and tokens[i - 1].isdigit()) or (
            i + 1 < len(tokens) and tokens[i + 1].isdigit()
        )
        if not near:
            continue
        for month, forms in _MONTHS.items():
            if any(token == f or (len(f) >= 4 and token.startswith(f)) for f in forms):
                values[month] += 1
                break
    return values


def _name_key(text: str) -> str:
    key = normalize(to_latin(text)).replace("'", "")
    for old, new in (
        ("shch", "sh"), ("dzh", "j"), ("dj", "j"), ("zh", "j"), ("kh", "x"), ("ts", "s"),
        ("ye", "e"), ("yo", "o"), ("yu", "u"), ("ya", "a"), ("iy", "i"), ("y", "i"),
        ("q", "k"), ("w", "v"), ("h", "x"),
    ):  # fmt: skip
        key = key.replace(old, new)
    return re.sub(r"(.)\1+", r"\1", key)


def surnames(text: str) -> list[str]:
    return list(dict.fromkeys(_SURNAME.findall(to_latin(text))))


@dataclass(slots=True)
class QualityReport:
    missing_numbers: list[str] = field(default_factory=list)
    extra_numbers: list[str] = field(default_factory=list)
    links_changed: list[str] = field(default_factory=list)
    names_to_check: list[str] = field(default_factory=list)
    terms_missing: list[str] = field(default_factory=list)
    terms_used: int = 0
    empty_paragraphs: list[int] = field(default_factory=list)
    untranslated_paragraphs: list[int] = field(default_factory=list)
    length_warnings: list[int] = field(default_factory=list)
    script_note: str | None = None
    ambiguities: list[str] = field(default_factory=list)
    paragraphs: int = 0

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.missing_numbers,
                self.extra_numbers,
                self.links_changed,
                self.names_to_check,
                self.terms_missing,
                self.empty_paragraphs,
                self.untranslated_paragraphs,
                self.script_note,
            )
        )

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "paragraphs": self.paragraphs,
            "missing_numbers": self.missing_numbers,
            "extra_numbers": self.extra_numbers,
            "links_changed": self.links_changed,
            "names_to_check": self.names_to_check,
            "terms_missing": self.terms_missing,
            "terms_used": self.terms_used,
            "empty_paragraphs": self.empty_paragraphs,
            "untranslated_paragraphs": self.untranslated_paragraphs,
            "length_warnings": self.length_warnings,
            "script_note": self.script_note,
            "ambiguities": self.ambiguities,
        }

    def lines(self) -> list[str]:
        """Warnings in plain words (for the chat and the UI)."""
        out: list[str] = []
        if self.missing_numbers:
            out.append(
                "Numbers in the source but not in the translation: "
                + ", ".join(self.missing_numbers[:12])
            )
        if self.extra_numbers:
            out.append(
                "Numbers in the translation that are not in the source: "
                + ", ".join(self.extra_numbers[:12])
            )
        if self.links_changed:
            out.append(
                "Links or e-mail addresses changed or missing: " + ", ".join(self.links_changed[:6])
            )
        if self.names_to_check:
            out.append(
                "Names to check (not found unchanged in the translation): "
                + ", ".join(self.names_to_check[:10])
            )
        if self.terms_missing:
            out.append("Glossary terms not used: " + "; ".join(self.terms_missing[:10]))
        if self.empty_paragraphs:
            out.append(f"{len(self.empty_paragraphs)} paragraph(s) came back empty")
        if self.untranslated_paragraphs:
            out.append(f"{len(self.untranslated_paragraphs)} paragraph(s) look untranslated")
        if self.length_warnings:
            out.append(
                f"{len(self.length_warnings)} paragraph(s) changed length a lot (check for omissions or additions)"
            )
        if self.script_note:
            out.append(self.script_note)
        if self.ambiguities:
            out.append(
                "Ambiguous places noted by the translator: " + "; ".join(self.ambiguities[:8])
            )
        return out


def check(
    pairs: list[tuple[str, str]],
    *,
    source_language: str,
    target_language: str,
    terms: list[Term] | None = None,
    notes: list[str] | None = None,
) -> QualityReport:
    """Compare a translation with its source, paragraph by paragraph (`pairs` of
    (source, translation)); a whole text is one pair."""
    report = QualityReport(paragraphs=len(pairs), ambiguities=list(notes or []))
    translating = base(source_language) != base(target_language)
    for index, (src, tgt) in enumerate(pairs):
        if not src.strip():
            continue
        if not tgt.strip():
            report.empty_paragraphs.append(index)
            continue
        letters = len(re.findall(r"[^\W\d_]", src))
        if translating and letters >= 12:
            same = normalize(src).strip() == normalize(tgt).strip()
            wrong_language = (
                len(tgt) >= 60 and base(detect(tgt)) == base(source_language) and not same
            )
            if same or wrong_language:
                report.untranslated_paragraphs.append(index)
        if translating and len(src) >= 80 and not 0.4 <= len(tgt) / len(src) <= 2.5:
            report.length_warnings.append(index)
    source = "\n\n".join(s for s, _ in pairs)
    target = "\n\n".join(t for _, t in pairs)
    src_numbers, tgt_numbers = numbers(source), numbers(target)
    report.missing_numbers = [str(n) for n in sorted((src_numbers - tgt_numbers).elements())]
    report.extra_numbers = [str(n) for n in sorted((tgt_numbers - src_numbers).elements())]
    report.links_changed = [
        link for link in dict.fromkeys(_LINKS.findall(source)) if link not in target
    ]
    target_keys = {_name_key(w) for w in re.findall(r"[^\W\d_][\w'ʻʼ‘’]*", target)}
    for name in surnames(source):
        key = _name_key(name)
        stem = key[: max(4, len(key) - 1)]
        if not any(k.startswith(stem) for k in target_keys):
            report.names_to_check.append(name)
    if terms:
        missing = missing_in(terms, source, target, source_language, target_language)
        report.terms_missing = [f"“{t.source}” → “{t.target}”" for t in missing]
        report.terms_used = len(relevant(terms, source, source_language)) - len(missing)
    script = detect_script(target)
    if target_language == "uz-cyrl" and script == "latin":
        report.script_note = "The translation is in Latin script; Cyrillic was asked"
    elif target_language == "uz" and script == "cyrillic":
        report.script_note = "The translation is in Cyrillic script; Latin was asked"
    report.ambiguities += [f"[?] ×{target.count('[?]')}"] if "[?]" in target else []
    return report
