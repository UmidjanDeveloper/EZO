"""Observable, deterministic feedback for IELTS-style text practice.

Everything here is computed from the transcript. No band, pronunciation or
"fluency score" is produced: that needs a model assessment (see assessment.py) or
audio analysis, neither of which runs on this path.

The thresholds below are EZO practice heuristics chosen for coaching hints. They are
NOT official IELTS band descriptors or criteria, and meeting or missing one says
nothing about a band. Speaking time is whatever the client reported; EZO does not
receive or analyse audio here, so pace derived from it is never verified.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from ezo_api.language.analysis import TextMetrics, measure

AnswerKind = Literal["part1", "part2_long_turn", "part2_follow_up", "part3"]
TimingSource = Literal["none", "client_reported"]

# --- non-official practice heuristics (not IELTS criteria) -------------------------------
HEURISTIC_MIN_WORDS: dict[AnswerKind, int] = {
    "part1": 15,
    "part2_long_turn": 80,
    "part2_follow_up": 5,
    "part3": 25,
}
HEURISTIC_LOW_DIVERSITY = 0.55
HEURISTIC_DIVERSITY_MIN_WORDS = 30
HEURISTIC_FILLER_RATE = 3.0
HEURISTIC_SHORT_SENTENCE_WORDS = 7.0
HEURISTIC_WPM_LOW, HEURISTIC_WPM_HIGH = 90.0, 190.0

HEURISTIC_NOTICE_EN = (
    "Observations use EZO practice heuristics, not official IELTS band criteria; "
    "no band, pronunciation or audio assessment was performed."
)
HEURISTIC_NOTICE_UZ = (
    "Kuzatuvlar EZO mashq evristikalariga asoslangan, rasmiy IELTS baholash mezonlari emas; "
    "band, talaffuz yoki audio tahlili bajarilmagan."
)


def answer_kind(part: int, index_in_part: int) -> AnswerKind:
    """Which answer this is, from the part it was given in and its 0-based position there."""
    if part == 2:
        return "part2_long_turn" if index_in_part == 0 else "part2_follow_up"
    return "part3" if part == 3 else "part1"


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    part: int
    kind: AnswerKind
    reported_seconds: float | None = None


@dataclass(slots=True)
class Notes:
    uz: list[str] = field(default_factory=list)
    en: list[str] = field(default_factory=list)

    def add(self, uz: str, en: str) -> None:
        self.uz.append(uz)
        self.en.append(en)


def _reported_seconds(answers: Sequence[Answer]) -> float | None:
    """Total client-reported time, only when every answer reported one (else pace is wrong)."""
    seconds = [a.reported_seconds for a in answers]
    if not seconds or any(s is None for s in seconds):
        return None
    return sum(s for s in seconds if s is not None)


def _length_notes(answers: Sequence[Answer], notes: Notes) -> None:
    if len(answers) == 1:
        a = answers[0]
        words = measure([a.text]).words
        target = HEURISTIC_MIN_WORDS[a.kind]
        if 0 < words < target:
            notes.add(
                f"Javob qisqa ({words} so'z); EZO evristikasi bu javob turi uchun "
                f"taxminan {target}+ so'zni tavsiya qiladi.",
                f"Short answer ({words} words); EZO's practice heuristic suggests about "
                f"{target}+ words for this answer type.",
            )
        return
    short = [a for a in answers if measure([a.text]).words < HEURISTIC_MIN_WORDS[a.kind]]
    if short:
        notes.add(
            f"{len(answers)} ta javobdan {len(short)} tasi EZO uzunlik evristikasidan qisqa.",
            f"{len(short)} of {len(answers)} answers are shorter than EZO's length heuristic "
            "for their answer type.",
        )


def _metric_notes(m: TextMetrics, notes: Notes) -> None:
    if m.fillers and m.filler_rate >= HEURISTIC_FILLER_RATE:
        notes.add(
            f"To'ldiruvchi so'zlar ko'p: {m.fillers} ta (100 so'zga {m.filler_rate:g}).",
            f"Many fillers: {m.fillers} ({m.filler_rate:g} per 100 words).",
        )
    if m.words >= HEURISTIC_DIVERSITY_MIN_WORDS and m.lexical_diversity < HEURISTIC_LOW_DIVERSITY:
        notes.add(
            f"Lug'at xilma-xilligi past ({m.lexical_diversity:.2f}); sinonimlardan foydalaning.",
            f"Low lexical variety ({m.lexical_diversity:.2f}); try synonyms.",
        )
    if m.repeated:
        words = ", ".join(f"{w} x{n}" for w, n in m.repeated)
        notes.add(f"Takrorlangan so'zlar: {words}.", f"Repeated words: {words}.")
    if (
        m.sentences
        and m.words >= HEURISTIC_DIVERSITY_MIN_WORDS
        and m.words_per_sentence < HEURISTIC_SHORT_SENTENCE_WORDS
    ):
        notes.add(
            "Gaplar juda qisqa; bog'lovchilar bilan uzunroq gaplar tuzing.",
            "Very short sentences; combine ideas with linking words.",
        )
    if m.words_per_minute is not None:
        if m.words_per_minute < HEURISTIC_WPM_LOW:
            notes.add(
                f"Mijoz bildirgan vaqt bo'yicha tezlik {m.words_per_minute:g} so'z/daq - sekin "
                "(audio tekshirilmagan).",
                f"Pace {m.words_per_minute:g} wpm from client-reported time - slow "
                "(audio not analysed).",
            )
        elif m.words_per_minute > HEURISTIC_WPM_HIGH:
            notes.add(
                f"Mijoz bildirgan vaqt bo'yicha tezlik {m.words_per_minute:g} so'z/daq - juda tez "
                "(audio tekshirilmagan).",
                f"Pace {m.words_per_minute:g} wpm from client-reported time - very fast "
                "(audio not analysed).",
            )


@dataclass(frozen=True, slots=True)
class Measured:
    metrics: TextMetrics
    timing_source: TimingSource
    notes: Notes
    """Empty for overall statistics, which carry numbers only."""


def measure_group(answers: Sequence[Answer], *, with_notes: bool = True) -> Measured:
    seconds = _reported_seconds(answers)
    m = measure([a.text for a in answers], seconds)
    timing: TimingSource = "client_reported" if m.words_per_minute is not None else "none"
    if not with_notes:
        return Measured(m, timing, Notes())
    notes = Notes()
    if m.words == 0:
        notes.add("Javobda inglizcha so'z topilmadi.", "No English words were found.")
        return Measured(m, timing, notes)
    _length_notes(answers, notes)
    _metric_notes(m, notes)
    if not notes.en:
        notes.add(
            "EZO evristikalari bo'yicha alohida kuzatuv yo'q (bu baho emas).",
            "Nothing flagged by EZO's practice heuristics (this is not a band).",
        )
    return Measured(m, timing, notes)
