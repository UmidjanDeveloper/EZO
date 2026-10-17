"""Intent classification.

A transparent, rule-based multilingual (uz/en/ru) classifier. Every decision
records which signals matched, so routing is easy to debug. A model-based
classifier can replace it later behind the same `classify_intent` function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ezo_api.core.text import normalize


class Intent(StrEnum):
    GENERAL = "general"
    LANGUAGE_COACH = "language_coach"
    PRESENTATION = "presentation"
    DEVELOPER = "developer"
    LEGAL_RESEARCH = "legal_research"
    RESEARCH = "research"
    DOCUMENT = "document"
    BUSINESS = "business"
    VISUAL = "visual"


# Each signal is a regex (matched against normalized text) and a weight.
# Patterns start at a word boundary so "kod" does not match "kodeks".
_SIGNALS: dict[Intent, list[tuple[str, float]]] = {
    Intent.LANGUAGE_COACH: [
        (r"\bielts\b", 3),
        (r"\bcefr\b", 2),
        (r"\benglish speaking\b", 3),
        (r"\bspeaking\b", 2),
        (r"\bingliz tili", 3),
        (r"\binglizcha\b", 2),
        (r"\bpractice english\b", 3),
        (r"\bpractise english\b", 3),
        (r"\bgrammar\b", 1.5),
        (r"\bgrammatika", 1.5),
        (r"\bvocabulary\b", 1.5),
        (r"\bpronunciation\b", 2),
        (r"\btalaffuz", 2),
        (r"\bанглийск", 3),
        (r"\bразговорн", 1.5),
        (r"\bпроизношени", 2),
        (r"\bspeak english\b", 3),
        (r"\bjob interview\b", 1.5),
        (r"\btil o'rgan", 2),
        (r"\bлексик", 1),
    ],
    Intent.PRESENTATION: [
        (r"\bpresentation", 3),
        (r"\bprezentatsiya", 3),
        (r"\btaqdimot", 3),
        (r"\bslides?\b", 2.5),
        (r"\bslayd", 2.5),
        (r"\bpptx?\b", 2.5),
        (r"\bпрезентаци", 3),
        (r"\bслайд", 2.5),
        (r"\bpitch deck\b", 2),
    ],
    Intent.DEVELOPER: [
        (r"\bgithub\b", 3),
        (r"\bgit\b", 2),
        (r"\bbug", 2.5),
        (r"\bdebug", 3),
        (r"\brepo(sitory)?\b", 2.5),
        (r"\bpull request\b", 3),
        (r"\bcode\b", 2),
        (r"\bkod\b", 2),
        (r"\bkodni\b", 2),
        (r"\bkodim", 2),
        (r"\bdasturla", 2),
        (r"\bpython\b", 2),
        (r"\bjavascript\b", 2),
        (r"\btypescript\b", 2),
        (r"\breact\b", 1.5),
        (r"\bfastapi\b", 2),
        (r"\bfunction\b", 1),
        (r"\bfunksiya", 1),
        (r"\bstack ?trace\b", 2.5),
        (r"\bкод\b", 2),
        (r"\bбаг", 2),
        (r"\bпрограммирова", 2),
        (r"\bcompile", 1.5),
        (r"\bunit test", 2),
    ],
    Intent.LEGAL_RESEARCH: [
        (r"\bqonun", 3),
        (r"\bfarmon", 3),
        (r"\bprezident qaror", 3.5),
        (r"\bqarori\b", 2),
        (r"\bkodeks", 3),
        (r"\blex\.uz\b", 4),
        (r"\bnizom", 1.5),
        (r"\bvazirlar mahkamasi", 3),
        (r"\bзакон", 3),
        (r"\bуказ", 3),
        (r"\bпостановлени", 3),
        (r"\bкодекс", 3),
        (r"\bdecree\b", 3),
        (r"\blaw\b", 2.5),
        (r"\blegal\b", 2),
        (r"\bhuquq", 2),
        (r"\bjarima", 1.5),
        (r"\bсоглашени", 1),
    ],
    Intent.RESEARCH: [
        (r"\bresearch\b", 3),
        (r"\btadqiq", 3),
        (r"\bmanba", 2),
        (r"\bsources?\b", 2),
        (r"\bfact.?check", 3),
        (r"\bсравни", 1.5),
        (r"\bисследова", 3),
        (r"\bисточник", 2),
        (r"\blatest news\b", 2.5),
        (r"\byangilik", 2),
        (r"\bновост", 2),
        (r"\bsolishtir", 1.5),
        (r"\bcompare\b", 1.5),
    ],
    Intent.DOCUMENT: [
        (r"\bpdf\b", 3),
        (r"\bdocx?\b", 3),
        (r"\bxlsx\b", 3),
        (r"\bexcel\b", 2.5),
        (r"\bcsv\b", 2.5),
        (r"\bhujjat", 2.5),
        (r"\bdocument\b", 2),
        (r"\bдокумент", 2.5),
        (r"\bspreadsheet\b", 2.5),
        (r"\bжадвал|\bjadval", 1.5),
        (r"\bтаблиц", 1.5),
        (r"\bproofread", 2),
        (r"\bscan", 1),
    ],
    Intent.BUSINESS: [
        (r"\bbiznes", 3),
        (r"\bbusiness\b", 3),
        (r"\bstartup", 2.5),
        (r"\bmarketing", 2.5),
        (r"\bswot\b", 3),
        (r"\braqobatchi", 2.5),
        (r"\bcompetitors?\b", 2.5),
        (r"\bбизнес", 3),
        (r"\bmarket research\b", 3),
        (r"\bbozor", 1.5),
        (r"\bpricing\b", 2),
        (r"\bmvp\b", 2),
        (r"\bdaromad", 1.5),
        (r"\brevenue\b", 1.5),
        (r"\bмаркетинг", 2.5),
    ],
    Intent.VISUAL: [
        (r"\brasm (chiz|yarat|yasa|gener)", 3),
        (r"\bgenerate an? image\b", 3),
        (r"\bdraw\b", 2),
        (r"\blogo", 2.5),
        (r"\blogotip", 2.5),
        (r"\billustration", 2),
        (r"\bкартинк", 2.5),
        (r"\bизображени", 2.5),
        (r"\bнарисуй", 3),
        (r"\bposter\b", 1.5),
    ],
}

_COMPILED = {
    intent: [(re.compile(pattern), weight) for pattern, weight in signals]
    for intent, signals in _SIGNALS.items()
}

MIN_SCORE = 2.0
"""Below this total weight the message is treated as general conversation."""


@dataclass(frozen=True, slots=True)
class IntentResult:
    intent: Intent
    confidence: float
    signals: tuple[str, ...]
    scores: dict[str, float]


def classify_intent(text: str) -> IntentResult:
    lowered = normalize(text)
    scores: dict[Intent, float] = {}
    matched: dict[Intent, list[str]] = {}
    for intent, signals in _COMPILED.items():
        for pattern, weight in signals:
            found = pattern.search(lowered)
            if found:
                scores[intent] = scores.get(intent, 0.0) + weight
                matched.setdefault(intent, []).append(found.group(0))

    readable_scores = {i.value: s for i, s in sorted(scores.items(), key=lambda kv: -kv[1])}
    if not scores:
        return IntentResult(Intent.GENERAL, 0.6, (), {})

    best, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score < MIN_SCORE:
        return IntentResult(Intent.GENERAL, 0.5, tuple(matched[best]), readable_scores)

    total = sum(scores.values())
    # Confidence grows with signal strength and with the margin over the rest.
    confidence = min(0.98, 0.5 + 0.08 * best_score) * (best_score / total) ** 0.5
    return IntentResult(best, round(confidence, 2), tuple(matched[best]), readable_scores)
