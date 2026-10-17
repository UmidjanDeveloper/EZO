"""Deterministic measurements of a learner's speech or writing (no model involved).

These numbers are *computed* from the transcript, so they are exact for what was
transcribed. They are evidence for the assessment, not band scores themselves.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE = re.compile(r"[.!?]+")
# Hesitation and filler expressions (multi-word ones are counted as one filler).
FILLERS = (
    "um",
    "uh",
    "er",
    "erm",
    "hmm",
    "you know",
    "i mean",
    "sort of",
    "kind of",
    "like i said",
    "basically",
    "actually",
)
_FILLER = re.compile(r"\b(" + "|".join(re.escape(f) for f in FILLERS) + r")\b", re.IGNORECASE)
STOPWORDS = frozenset(
    "a an the and or but so to of in on at for with is are was were be been am i you he she it "
    "we they my your his her its our their me him us them this that these those there here "
    "do does did have has had not no yes very really just also then than as by from about "
    "what which who when where why how can could would should will".split()
)
MATTR_WINDOW = 50


@dataclass(frozen=True, slots=True)
class TextMetrics:
    words: int
    unique_words: int
    lexical_diversity: float
    """Moving-average type/token ratio (window of 50 words); 0..1, higher = more varied."""
    sentences: int
    words_per_sentence: float
    fillers: int
    filler_rate: float
    """Fillers per 100 words."""
    repeated: list[tuple[str, int]] = field(default_factory=list)
    """Content words used unusually often (word, count)."""
    speech_seconds: float | None = None
    words_per_minute: float | None = None
    """Only when the speaking time was measured (voice turns)."""


def words_of(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def lexical_diversity(words: list[str], window: int = MATTR_WINDOW) -> float:
    if not words:
        return 0.0
    if len(words) <= window:
        return round(len(set(words)) / len(words), 3)
    ratios = [len(set(words[i : i + window])) / window for i in range(len(words) - window + 1)]
    return round(sum(ratios) / len(ratios), 3)


def measure(texts: list[str], speech_seconds: float | None = None) -> TextMetrics:
    joined = "\n".join(texts)
    words = words_of(joined)
    sentences = max(len([s for s in _SENTENCE.split(joined) if s.strip()]), 1 if words else 0)
    fillers = len(_FILLER.findall(joined))
    content = Counter(w for w in words if w not in STOPWORDS and len(w) > 2)
    threshold = max(3, len(words) // 40)
    repeated = [(w, n) for w, n in content.most_common(8) if n >= threshold][:5]
    wpm = None
    if speech_seconds and speech_seconds >= 5 and words:
        wpm = round(len(words) / (speech_seconds / 60), 1)
    return TextMetrics(
        words=len(words),
        unique_words=len(set(words)),
        lexical_diversity=lexical_diversity(words),
        sentences=sentences,
        words_per_sentence=round(len(words) / sentences, 1) if sentences else 0.0,
        fillers=fillers,
        filler_rate=round(100 * fillers / len(words), 2) if words else 0.0,
        repeated=repeated,
        speech_seconds=round(speech_seconds, 1) if speech_seconds else None,
        words_per_minute=wpm,
    )


def describe(metrics: TextMetrics) -> str:
    """The measurements as plain facts for prompts and reports."""
    parts = [
        f"{metrics.words} words ({metrics.unique_words} different)",
        f"lexical diversity {metrics.lexical_diversity:.2f}",
        f"{metrics.words_per_sentence:g} words per sentence",
        f"{metrics.fillers} fillers ({metrics.filler_rate:g} per 100 words)",
    ]
    if metrics.words_per_minute is not None:
        parts.append(
            f"{metrics.words_per_minute:g} words per minute over {metrics.speech_seconds:g} s "
            "of measured speaking time"
        )
    if metrics.repeated:
        parts.append("often repeated: " + ", ".join(f"{w} ×{n}" for w, n in metrics.repeated))
    return "; ".join(parts)
