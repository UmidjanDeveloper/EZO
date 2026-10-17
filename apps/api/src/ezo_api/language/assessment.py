# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""Turn a practice transcript into a validated, honest assessment.

The model proposes scores, mistakes and suggestions as JSON; this module then
checks them. It rounds bands to halves and clamps them to 0–9. It drops "mistakes"
whose original text the learner never said, maps categories to a fixed list, and
withholds band estimates when there is too little speech. Pronunciation is only
estimated from voice transcripts and is labelled transcript-assisted. It is never
part of the overall range, because no acoustic analysis exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ezo_api.core.text import normalize
from ezo_api.db.models.language import MISTAKE_CATEGORIES
from ezo_api.language.ielts import band_range, round_band

MIN_WORDS_FOR_BANDS = 40
MAX_MISTAKES = 25

# EZO's own short description of the four IELTS speaking criteria (not the official
# descriptor text; owners can add the official public descriptors to the knowledge base).
CRITERIA_GUIDE = """Assess the four IELTS speaking criteria (bands 0–9, half bands allowed):
- Fluency and Coherence: speaking at length without unnatural hesitation, logical order, use of linking words, staying on topic.
- Lexical Resource: range and precision of vocabulary, collocations and idiomatic language, ability to paraphrase.
- Grammatical Range and Accuracy: variety of structures (complex sentences, tenses, conditionals) and how often errors occur and whether they block meaning.
- Pronunciation: only judged from sound. You receive only a transcript, so return null unless told the session was spoken; even then give at most a cautious transcript-assisted estimate."""

ASSESSMENT_SYSTEM = f"""You are EZO's language assessor for an IELTS-style practice simulator (not an official examiner; every band is an estimate).
{CRITERIA_GUIDE}

Rules:
- Judge ONLY the learner's turns. Base every band on evidence you can quote.
- Use the computed measurements given (they are exact for the transcript); do not contradict them.
- Mistakes: quote the learner's exact words in "original" (copy them character for character), give a corrected version, a short explanation (one sentence) and a category from: {", ".join(MISTAKE_CATEGORIES)}. Severity "major" only if it blocks or changes meaning. Do not list a "mistake" that is actually correct.
- Strengths and weaknesses: concrete and specific to this learner.
- Better sentences: rewrite 2–4 of the learner's own sentences at a slightly higher level.
- Vocabulary: 3–6 useful words or collocations for the topics discussed, with meaning and an example.
- Practice target: one concrete thing to practise next.
- Write strengths, weaknesses, explanations, summary and practice target in {{feedback_language}}; keep quotes, corrections and examples in English.
Reply with ONLY one JSON object:
{{"fluency_coherence": {{"band": number|null, "evidence": str}}, "lexical_resource": {{...}}, "grammatical_range_accuracy": {{...}}, "pronunciation": {{"band": number|null, "evidence": str}}, "cefr_estimate": "A1"|"A2"|"B1"|"B2"|"C1"|"C2"|null, "strengths": [str], "weaknesses": [str], "mistakes": [{{"category": str, "original": str, "correction": str, "explanation": str, "severity": "minor"|"major"}}], "better_sentences": [{{"original": str, "improved": str}}], "vocabulary": [{{"term": str, "meaning": str, "example": str}}], "practice_target": str, "summary": str}}"""

CRITERIA = ("fluency_coherence", "lexical_resource", "grammatical_range_accuracy")
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")


@dataclass(slots=True)
class Mistake:
    category: str
    original: str
    correction: str
    explanation: str
    severity: str


@dataclass(slots=True)
class Assessment:
    scores: dict[str, float | None]
    """fluency_coherence, lexical_resource, grammatical_range_accuracy, pronunciation."""
    evidence: dict[str, str]
    band_low: float | None
    band_high: float | None
    pronunciation_confidence: str
    cefr_estimate: str | None
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    mistakes: list[Mistake] = field(default_factory=list)
    better_sentences: list[dict[str, str]] = field(default_factory=list)
    vocabulary: list[dict[str, str]] = field(default_factory=list)
    practice_target: str = ""
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    """Honesty notes (e.g. "too little speech for a band estimate")."""
    dropped_mistakes: int = 0


def _band(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:  # NaN or negative
        return None
    return round_band(number)


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _strings(value: Any, limit: int, count: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (_text(v, limit) for v in value) if t][:count]


def validate(
    data: dict[str, Any] | None,
    *,
    learner_text: str,
    learner_words: int,
    spoken_share: float,
) -> Assessment:
    """Check and normalise a model assessment. `data=None` → measurements-only assessment."""
    data = data or {}
    scores: dict[str, float | None] = {}
    evidence: dict[str, str] = {}
    notes: list[str] = []
    enough = learner_words >= MIN_WORDS_FOR_BANDS
    for key in (*CRITERIA, "pronunciation"):
        raw_item = data.get(key)
        item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
        scores[key] = _band(item.get("band")) if enough else None
        evidence[key] = _text(item.get("evidence"), 600)
    if not enough:
        notes.append(
            f"Only {learner_words} words were spoken or written; at least {MIN_WORDS_FOR_BANDS} "
            "are needed for a band estimate, so no band is given."
        )
    if spoken_share < 0.5:
        scores["pronunciation"] = None
        confidence = "not_assessed"
        notes.append("Pronunciation was not assessed: the session was mostly typed.")
    elif scores["pronunciation"] is None:
        confidence = "not_assessed"
    else:
        confidence = "transcript_assisted"
        notes.append(
            "Pronunciation is a cautious transcript-assisted estimate (no acoustic analysis); "
            "it is not included in the overall range."
        )
    assessed = [s for k in CRITERIA if (s := scores[k]) is not None]
    low = high = None
    if assessed:
        low, high = band_range(assessed, learner_words)

    norm_learner = normalize(" ".join(learner_text.split()))
    mistakes: list[Mistake] = []
    dropped = 0
    for raw in data.get("mistakes") or []:
        if not isinstance(raw, dict):
            continue
        original = _text(raw.get("original"), 300)
        correction = _text(raw.get("correction"), 300)
        if not original or not correction or normalize(original) == normalize(correction):
            dropped += 1
            continue
        if normalize(original) not in norm_learner:  # the learner never said this
            dropped += 1
            continue
        category = _text(raw.get("category"), 30).lower().replace(" ", "_")
        mistakes.append(
            Mistake(
                category=category if category in MISTAKE_CATEGORIES else "other",
                original=original,
                correction=correction,
                explanation=_text(raw.get("explanation"), 300),
                severity="major" if raw.get("severity") == "major" else "minor",
            )
        )
        if len(mistakes) >= MAX_MISTAKES:
            break
    cefr = _text(data.get("cefr_estimate"), 2).upper() or None
    better = [
        {"original": _text(b.get("original"), 300), "improved": _text(b.get("improved"), 300)}
        for b in data.get("better_sentences") or []
        if isinstance(b, dict) and b.get("original") and b.get("improved")
    ][:4]
    vocabulary = [
        {
            "term": _text(v.get("term"), 120),
            "meaning": _text(v.get("meaning"), 300),
            "example": _text(v.get("example"), 300),
        }
        for v in data.get("vocabulary") or []
        if isinstance(v, dict) and _text(v.get("term"), 120)
    ][:6]
    return Assessment(
        scores=scores,
        evidence=evidence,
        band_low=low,
        band_high=high,
        pronunciation_confidence=confidence,
        cefr_estimate=cefr if cefr in CEFR and enough else None,
        strengths=_strings(data.get("strengths"), 300, 5),
        weaknesses=_strings(data.get("weaknesses"), 300, 5),
        mistakes=mistakes,
        better_sentences=better,
        vocabulary=vocabulary,
        practice_target=_text(data.get("practice_target"), 400),
        summary=_text(data.get("summary"), 800),
        notes=notes,
        dropped_mistakes=dropped,
    )
