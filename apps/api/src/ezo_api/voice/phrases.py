"""Repeatable voice test phrases and objective transcript comparison.

The owner (or CI with real keys, never this repository) speaks or synthesises each phrase,
transcribes the result and compares it with the reference: word error rate (WER) and
character error rate (CER) after a deterministic normalisation. Uzbek references are
compared in Latin script (a Cyrillic transcript is transliterated first), apostrophe
variants are unified, punctuation and case are ignored. These numbers are evidence of
recognition quality for a *recording*; they say nothing about how natural a voice sounds —
that stays a listening test by a native speaker.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ezo_api.translation.translit import detect_script, to_latin

Language = str  # "uz" | "en" | "ru"

# Short, everyday, phonetically varied phrases: numbers, names, apostrophe words, a question.
TEST_PHRASES: dict[Language, tuple[str, ...]] = {
    "uz": (
        "Salom EZO, bugun ob-havo qanday?",
        "Ertaga soat o'nda uchrashuvni eslatib qo'y.",
        "Downloads papkasidagi oxirgi faylni och.",
        "Bu hujjatdagi foiz ko'rsatkichlarini hisobla.",
        "Rahmat, hozircha shu yetarli.",
    ),
    "en": (
        "Hello EZO, what is the weather today?",
        "Remind me about the meeting at ten tomorrow.",
        "Open the latest file in the Downloads folder.",
        "Calculate the percentages in this document.",
        "Thank you, that is enough for now.",
    ),
    "ru": (
        "Привет EZO, какая сегодня погода?",
        "Напомни о встрече завтра в десять.",
        "Открой последний файл в папке Загрузки.",
        "Посчитай проценты в этом документе.",
        "Спасибо, пока достаточно.",
    ),
}

_APOSTROPHES = "‘’ʻʼ`´′"
_PUNCTUATION = re.compile(r"[^\w\s']", flags=re.UNICODE)


def normalize(text: str, language: Language | None = None) -> str:
    """Lower-case, unify apostrophes, drop punctuation, collapse spaces; Uzbek → Latin."""
    value = unicodedata.normalize("NFC", text)
    for ch in _APOSTROPHES:
        value = value.replace(ch, "'")
    if language == "uz" and detect_script(value) == "cyrillic":
        value = to_latin(value)
    value = value.casefold().replace("ё", "е")
    value = _PUNCTUATION.sub(" ", value)
    return " ".join(value.split())


def _edit_distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        current = [i]
        for j, y in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class Comparison:
    reference: str
    hypothesis: str
    wer: float
    cer: float

    @property
    def exact(self) -> bool:
        return self.wer == 0.0


def compare(reference: str, hypothesis: str, language: Language | None = None) -> Comparison:
    """WER/CER of a transcript against its reference (0.0 = identical after normalisation)."""
    ref = normalize(reference, language)
    hyp = normalize(hypothesis, language)
    ref_words, hyp_words = ref.split(), hyp.split()
    wer = _edit_distance(ref_words, hyp_words) / max(1, len(ref_words))
    cer = _edit_distance(list(ref), list(hyp)) / max(1, len(ref))
    return Comparison(ref, hyp, round(wer, 4), round(cer, 4))
