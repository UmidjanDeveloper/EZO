"""Read-aloud pronunciation check: the learner reads a sentence, EZO compares what the speech
recognizer heard with what should have been said.

Honest by construction: this is *recognition-based*, not phoneme-level. A word counts as
wrong when the recognizer (told which language to expect) heard a different word — the usual
sign that it was mispronounced, skipped or swallowed. Speaking rate comes from the recording's
length. The score is an estimate for practice, never an exam band.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MAX_REFERENCE_CHARS = 600
_WORD = re.compile(r"[^\W_]+(?:['’ʼ‘-][^\W_]+)*", re.UNICODE)
# Comfortable reading pace (words per minute) for a learner reading aloud.
SLOW_WPM, FAST_WPM = 80, 190

WordStatus = Literal["ok", "close", "wrong", "missed"]

# Short sample sentences per language for the practice page.
SAMPLES: dict[str, list[str]] = {
    "en": [
        "The weather is beautiful today, so we are going to the park.",
        "I would like to improve my English pronunciation every day.",
        "Thirty three thirsty birds sat on the third branch.",
    ],
    "ru": [
        "Сегодня хорошая погода, поэтому мы идём в парк.",
        "Я каждый день читаю книги на русском языке.",
    ],
    "de": [
        "Heute ist das Wetter schön, deshalb gehen wir in den Park.",
        "Ich lerne jeden Tag ein bisschen Deutsch.",
    ],
    "fr": ["Aujourd'hui il fait beau, alors nous allons au parc."],
    "es": ["Hoy hace buen tiempo, así que vamos al parque."],
    "tr": ["Bugün hava çok güzel, bu yüzden parka gidiyoruz."],
    "uz": ["Bugun havo juda yaxshi, shuning uchun biz bog‘ga boramiz."],
}


@dataclass(frozen=True, slots=True)
class WordResult:
    word: str
    status: WordStatus
    heard: str | None = None


@dataclass(slots=True)
class PronunciationResult:
    score: int
    accuracy: float
    completeness: float
    words_per_minute: float | None
    pace: Literal["slow", "good", "fast"] | None
    words: list[WordResult] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    heard: str = ""
    to_practise: list[str] = field(default_factory=list)
    method: str = "recognition-based estimate (not phoneme-level)"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fold(word: str) -> str:
    """Lowercase, apostrophes unified, accents kept apart from the letter (é → e)."""
    word = word.lower().replace("’", "'").replace("ʼ", "'").replace("‘", "'")
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).replace("ё", "е")


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def score_reading(
    reference: str, heard: str, duration_ms: int | None = None
) -> PronunciationResult:
    ref_words = words(reference[:MAX_REFERENCE_CHARS])
    heard_words = words(heard)
    if not ref_words:
        raise ValueError("The sentence to read has no words.")
    ref_f = [_fold(w) for w in ref_words]
    heard_f = [_fold(w) for w in heard_words]
    matcher = difflib.SequenceMatcher(a=ref_f, b=heard_f, autojunk=False)
    results: list[WordResult | None] = [None] * len(ref_words)
    extra: list[str] = []
    credit = 0.0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i in range(i1, i2):
                results[i] = WordResult(ref_words[i], "ok")
                credit += 1
        elif tag in ("replace", "delete"):
            said = heard_words[j1:j2] if tag == "replace" else []
            said_f = heard_f[j1:j2] if tag == "replace" else []
            for k, i in enumerate(range(i1, i2)):
                if k < len(said):
                    ratio = difflib.SequenceMatcher(a=ref_f[i], b=said_f[k]).ratio()
                    status: WordStatus = "close" if ratio >= 0.75 else "wrong"
                    credit += 0.5 if status == "close" else 0
                    results[i] = WordResult(ref_words[i], status, said[k])
                else:
                    results[i] = WordResult(ref_words[i], "missed")
            extra.extend(said[i2 - i1 :])
        elif tag == "insert":
            extra.extend(heard_words[j1:j2])
    final = [r for r in results if r is not None]
    accuracy = credit / len(ref_words)
    completeness = sum(1 for r in final if r.status != "missed") / len(ref_words)
    wpm: float | None = None
    pace: Literal["slow", "good", "fast"] | None = None
    if duration_ms and duration_ms > 500 and heard_words:
        wpm = round(len(heard_words) / (duration_ms / 60_000), 1)
        pace = "slow" if wpm < SLOW_WPM else "fast" if wpm > FAST_WPM else "good"
    penalty = min(0.1, 0.02 * len(extra)) + (0.05 if pace and pace != "good" else 0)
    score = max(0, min(100, round((0.8 * accuracy + 0.2 * completeness - penalty) * 100)))
    return PronunciationResult(
        score=score,
        accuracy=round(accuracy, 3),
        completeness=round(completeness, 3),
        words_per_minute=wpm,
        pace=pace,
        words=final,
        extra=extra,
        heard=heard,
        to_practise=[r.word for r in final if r.status != "ok"][:10],
    )
