"""Legal metadata from text: numbers, dates, types, status labels, scripts.

Rules (honesty first):
- Only what the text states is extracted. Nothing is guessed or defaulted.
- A document's status is read only from an explicit status *label*
  ("Holati: …", "Ҳолати: …", "Статус: …"), never from body wording: laws
  routinely declare *other* acts repealed, so "kuchini yo'qotgan" in a body says
  nothing about the document itself.
- Uzbek appears in Latin and Cyrillic script; Russian in Cyrillic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

APOSTROPHES = "'‘’ʻʼ`´"
_A = f"[{APOSTROPHES}]?"

# Number prefix → (document type, issuing authority). Latin, Cyrillic and Russian forms.
NUMBER_PREFIXES: dict[str, tuple[str, str]] = {
    "ORQ": ("law", "Oliy Majlis"),
    "ЎРҚ": ("law", "Oliy Majlis"),
    "ЗРУ": ("law", "Oliy Majlis"),
    "LRU": ("law", "Oliy Majlis"),
    "PF": ("presidential_decree", "President of the Republic of Uzbekistan"),
    "ПФ": ("presidential_decree", "President of the Republic of Uzbekistan"),
    "УП": ("presidential_decree", "President of the Republic of Uzbekistan"),
    "UP": ("presidential_decree", "President of the Republic of Uzbekistan"),
    "PQ": ("presidential_resolution", "President of the Republic of Uzbekistan"),
    "ПҚ": ("presidential_resolution", "President of the Republic of Uzbekistan"),
    "ПП": ("presidential_resolution", "President of the Republic of Uzbekistan"),
    "PP": ("presidential_resolution", "President of the Republic of Uzbekistan"),
    "VMQ": ("cabinet_resolution", "Cabinet of Ministers"),
    "ВМҚ": ("cabinet_resolution", "Cabinet of Ministers"),
    "ПКМ": ("cabinet_resolution", "Cabinet of Ministers"),
    "PKM": ("cabinet_resolution", "Cabinet of Ministers"),
}
_NUMBER = re.compile(
    rf"\b(O{_A}RQ|ЎРҚ|ЗРУ|LRU|PF|ПФ|УП|UP|PQ|ПҚ|ПП|PP|VMQ|ВМҚ|ПКМ|PKM)[-–]\s?(\d{{1,5}}(?:[-–]\d{{1,3}})?)",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_LEAD_DATE = re.compile(
    r"^(?:от\s+|dan\s+)?\d{2}\.\d{2}\.\d{4}\s*(?:г\.|йил|yil)?\.?\s*", re.IGNORECASE
)
_SON = re.compile(r"^[-–]?\s*(сон(ли)?|son(li)?)\b\.?", re.IGNORECASE)
_STATUS_LABEL = re.compile(
    r"^\s*(holati|ҳолати|статус|состояние|status)\s*[:\-–]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
STATUS_WORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"kuchini yo.qotgan|кучини йўқотган|утратил\w* силу|repealed", re.I), "repealed"),
    (re.compile(r"muddati tugagan|муддати тугаган|истек\w* срок|expired", re.I), "expired"),
    (
        re.compile(r"kuchga kirmagan|кучга кирмаган|не вступил\w*|not yet in force", re.I),
        "not_yet_in_force",
    ),
    (re.compile(r"amaldagi|амалдаги|действующ\w*|in force", re.I), "in_force"),
]
ARTICLE_HEADING = re.compile(
    r"^\s*(?:(\d{1,4}(?:\.\d{1,2})?)\s*[-–]\s*(modda|модда)|(статья|article)\s+(\d{1,4}(?:\.\d{1,2})?))\b"
    r"[^\n]{0,200}$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class TitleInfo:
    number: str | None
    document_type: str | None
    authority: str | None
    adopted_on: date | None
    title: str


def _date(day: str, month: str, year: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def normalize_prefix(prefix: str) -> str:
    cleaned = "".join(ch for ch in prefix.upper() if ch not in APOSTROPHES)
    return cleaned


def parse_title(raw: str) -> TitleInfo:
    """Number, type, authority and date from a title such as
    ``ЎРҚ-682-сон 20.04.2021. Норматив-ҳуқуқий ҳужжатлар тўғрисида``."""
    text = " ".join((raw or "").split())
    number = document_type = authority = None
    adopted: date | None = None
    rest = text
    match = _NUMBER.search(text)
    if match:
        prefix = normalize_prefix(match.group(1))
        number = f"{match.group(1)}-{match.group(2)}"
        document_type, authority = NUMBER_PREFIXES.get(prefix, (None, None))
        rest = text[match.end() :]
        rest = _SON.sub("", rest.lstrip())
    date_match = _DATE.search(rest if match else text)
    if date_match:
        adopted = _date(*date_match.groups())
    if match:
        rest = _LEAD_DATE.sub("", rest.lstrip())
    title = rest.strip(" .,-–:") if match else text
    return TitleInfo(number, document_type, authority, adopted, title or text)


def status_from_label(label: str) -> str | None:
    """Map an explicit status label to a status; None when it is not recognised."""
    for pattern, status in STATUS_WORDS:
        if pattern.search(label):
            return status
    return None


def explicit_status(text: str, header_chars: int = 2_000) -> str | None:
    """A status stated by a status label near the top of the document, if any."""
    match = _STATUS_LABEL.search(text[:header_chars])
    return status_from_label(match.group(2)) if match else None


def script_of(text: str) -> str | None:
    cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if not cyrillic and not latin:
        return None
    return "cyrl" if cyrillic > latin else "latn"


def mark_articles(text: str) -> str:
    """Turn article headings into Markdown headings so each article is its own section."""
    return ARTICLE_HEADING.sub(lambda m: "## " + m.group(0).strip(), text)


# --- Uzbek Cyrillic ↔ Latin (official 1995 alphabet), for search variants ----------------

_CYRL_TO_LATN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "ғ": "gʻ",
    "д": "d",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "қ": "q",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ў": "oʻ",
    "ф": "f",
    "х": "x",
    "ҳ": "h",
    "ц": "s",
    "ч": "ch",
    "ш": "sh",
    "ъ": "ʼ",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}
_VOWELS = set("аеёиоуўэюя")


def cyrl_to_latn(text: str) -> str:
    out: list[str] = []
    previous = ""
    for ch in text:
        lower = ch.lower()
        if lower == "е":
            mapped = (
                "ye"
                if (not previous or not previous.isalpha() or previous.lower() in _VOWELS)
                else "e"
            )
        else:
            mapped = _CYRL_TO_LATN.get(lower, ch if lower == ch else lower)
        if ch != lower and mapped:
            mapped = mapped[0].upper() + mapped[1:]
        out.append(mapped)
        previous = ch
    return "".join(out)


_LATN_TO_CYRL = [
    ("sh", "ш"),
    ("ch", "ч"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("ye", "е"),
    ("gʻ", "ғ"),
    ("g'", "ғ"),
    ("g‘", "ғ"),
    ("oʻ", "ў"),
    ("o'", "ў"),
    ("o‘", "ў"),
]
_LATN_SINGLE = {
    "a": "а",
    "b": "б",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "ҳ",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "қ",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "x": "х",
    "y": "й",
    "z": "з",
}


def latn_to_cyrl(text: str) -> str:
    """Approximate Latin → Cyrillic (good enough for search variants, not for display)."""
    lowered = text.lower()
    for latin, cyrillic in _LATN_TO_CYRL:
        lowered = lowered.replace(latin, cyrillic)
    return "".join(_LATN_SINGLE.get(ch, ch) for ch in lowered)


def query_variants(query: str) -> list[str]:
    """The query plus its other-script form (Uzbek Latin ↔ Cyrillic), without duplicates."""
    variants = [query]
    other = cyrl_to_latn(query) if script_of(query) == "cyrl" else latn_to_cyrl(query)
    if other.strip() and other.lower() != query.lower():
        variants.append(other)
    return variants
