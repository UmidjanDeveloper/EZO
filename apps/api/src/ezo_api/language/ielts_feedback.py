"""Observable, deterministic feedback for IELTS-style text practice.

Everything here is computed from the transcript. No band, pronunciation or
"fluency score" is produced: that needs a model assessment (see assessment.py) or
audio analysis, neither of which runs on this path.
"""

from __future__ import annotations

from ezo_api.language.analysis import TextMetrics, measure

# Typical full answers: Part 1 is a few sentences, Part 2 a 1-2 minute monologue.
_MIN_WORDS = {1: 15, 2: 80, 3: 25}
_WPM_LOW, _WPM_HIGH = 90.0, 190.0


def observations(m: TextMetrics, part: int) -> tuple[list[str], list[str]]:
    """Plain-fact notes (uz, en) derived from the measurements."""
    uz: list[str] = []
    en: list[str] = []
    target = _MIN_WORDS.get(part, 15)
    if m.words == 0:
        return (["Javobda inglizcha so'z topilmadi."], ["No English words were found."])
    if m.words < target:
        uz.append(
            f"Javob qisqa ({m.words} so'z); {part}-qism uchun taxminan {target}+ so'z kutiladi."
        )
        en.append(
            f"Short answer ({m.words} words); about {target}+ words are expected for Part {part}."
        )
    if m.fillers and m.filler_rate >= 3:
        uz.append(f"To'ldiruvchi so'zlar ko'p: {m.fillers} ta (100 so'zga {m.filler_rate:g}).")
        en.append(f"Many fillers: {m.fillers} ({m.filler_rate:g} per 100 words).")
    if m.words >= 30 and m.lexical_diversity < 0.55:
        uz.append(
            f"Lug'at xilma-xilligi past ({m.lexical_diversity:.2f}); sinonimlardan foydalaning."
        )
        en.append(f"Low lexical variety ({m.lexical_diversity:.2f}); try synonyms.")
    if m.repeated:
        words = ", ".join(f"{w} ×{n}" for w, n in m.repeated)
        uz.append(f"Takrorlangan so'zlar: {words}.")
        en.append(f"Repeated words: {words}.")
    if m.sentences and m.words >= 30 and m.words_per_sentence < 7:
        uz.append("Gaplar juda qisqa; bog'lovchilar bilan uzunroq gaplar tuzing.")
        en.append("Very short sentences; combine ideas with linking words.")
    if m.words_per_minute is not None:
        if m.words_per_minute < _WPM_LOW:
            uz.append(
                f"Nutq tezligi {m.words_per_minute:g} so'z/daq (o'lchangan vaqt bo'yicha) - sekin."
            )
            en.append(f"Speaking pace {m.words_per_minute:g} wpm over measured time - slow.")
        elif m.words_per_minute > _WPM_HIGH:
            uz.append(f"Nutq tezligi {m.words_per_minute:g} so'z/daq - juda tez.")
            en.append(f"Speaking pace {m.words_per_minute:g} wpm - very fast.")
    if not uz:
        uz.append("O'lchangan ko'rsatkichlarda alohida muammo topilmadi (bu baho emas).")
        en.append("No issue found in the measured indicators (this is not a band).")
    return uz, en


def measure_answers(answers: list[str], part: int, speech_seconds: float | None = None):
    m = measure(answers, speech_seconds)
    uz, en = observations(m, part)
    return m, uz, en
