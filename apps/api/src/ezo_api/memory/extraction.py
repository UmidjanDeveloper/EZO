"""Memory candidate extraction with importance scoring.

EZO does not store everything. A sentence becomes a memory candidate only when
it matches a meaningful pattern (explicit "remember", a preference, a goal, a
personal fact, a learning difficulty or a decision). Each pattern carries an
importance and confidence score; candidates below `MIN_IMPORTANCE` are dropped,
and sensitive content is never stored automatically.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ezo_api.core.text import normalize
from ezo_api.memory.sensitive import sensitive_reason

MIN_IMPORTANCE = 0.55
MAX_MEMORY_CHARS = 400


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    content: str
    category: str
    importance: float
    confidence: float
    explicit: bool


@dataclass(frozen=True, slots=True)
class _Rule:
    category: str
    importance: float
    confidence: float
    pattern: re.Pattern[str]
    explicit: bool = False
    strip_trigger: bool = False


def _rule(
    category: str,
    importance: float,
    confidence: float,
    pattern: str,
    explicit: bool = False,
    strip_trigger: bool = False,
) -> _Rule:
    return _Rule(category, importance, confidence, re.compile(pattern), explicit, strip_trigger)


_RULES: tuple[_Rule, ...] = (
    _rule(
        "explicit",
        0.9,
        0.95,
        r"\b(eslab qoling|eslab qol|yodda tut|yodingda tut|esingda tut|unutma|remember that|"
        r"remember:|please remember|don't forget|do not forget|запомни|не забудь)(?!\w)"
        r"[\s,:-]*",
        explicit=True,
        strip_trigger=True,
    ),
    _rule(
        "preference",
        0.65,
        0.8,
        r"\b(yoqtiraman|yaxshi ko'raman|afzal ko'raman|ma'qul ko'raman|menga .{1,40} yoqadi|"
        r"i prefer|i like|i love|i hate|i don't like|my favou?rite|я предпочитаю|мне нравится|"
        r"я люблю|не люблю|мой любимый|моя любимая)\b",
    ),
    _rule(
        "personal",
        0.75,
        0.85,
        r"\b(mening ismim|ismim|my name is|call me|меня зовут|men .{1,40}da ishlayman|"
        r"i work (at|as|in)|я работаю|men .{1,30}(da|dan) yashayman|i live in|я живу)\b",
    ),
    _rule(
        "goal",
        0.7,
        0.75,
        r"\b(maqsadim|rejam|niyatim|my goal|i want to become|i plan to|моя цель|я планирую|"
        r"хочу стать)\b",
    ),
    _rule(
        "learning",
        0.65,
        0.7,
        r"\b(qiynalaman|qiyinchilik|tushunmayman|i struggle with|i find .{1,30} hard|"
        r"my weakness|мне трудно|плохо понимаю|my ielts|ielts .{0,10}(band|ball))\b",
    ),
    _rule(
        "decision",
        0.6,
        0.7,
        r"\b(qaror qildim|qaror qildik|we decided|i decided|мы решили|я решил|я решила)\b",
    ),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_LEADING_ADDRESS = re.compile(r"^\s*(ezo|эзо)\s*[,!:.-]?\s*", re.IGNORECASE)


def _categorize(lowered: str) -> str:
    for rule in _RULES:
        if not rule.explicit and rule.pattern.search(lowered):
            return rule.category
    return "fact"


def extract_candidates(text: str) -> list[MemoryCandidate]:
    """Find memorable statements in a user message."""
    candidates: list[MemoryCandidate] = []
    seen: set[str] = set()
    for raw_sentence in _SENTENCE_SPLIT.split(text):
        sentence = _LEADING_ADDRESS.sub("", unicodedata.normalize("NFC", raw_sentence.strip()))
        if len(sentence) < 8 or sentence.endswith("?"):
            continue
        lowered = normalize(sentence)
        for rule in _RULES:
            match = rule.pattern.search(lowered)
            if not match:
                continue
            content = sentence
            if rule.strip_trigger:
                content = sentence[match.end() :].strip(" ,:-")
                if len(content) < 4:
                    break
            content = content[:MAX_MEMORY_CHARS].strip()
            key = normalize(content)
            category = _categorize(key) if rule.explicit else rule.category
            if rule.importance >= MIN_IMPORTANCE and key not in seen:
                seen.add(key)
                candidates.append(
                    MemoryCandidate(
                        content, category, rule.importance, rule.confidence, rule.explicit
                    )
                )
            break  # one rule per sentence: the first (most important) match wins
    return candidates


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    accepted: list[MemoryCandidate]
    skipped_sensitive: int


def extract_safe_candidates(text: str) -> ExtractionOutcome:
    accepted: list[MemoryCandidate] = []
    skipped = 0
    for candidate in extract_candidates(text):
        if sensitive_reason(candidate.content):
            skipped += 1
        else:
            accepted.append(candidate)
    return ExtractionOutcome(accepted, skipped)
