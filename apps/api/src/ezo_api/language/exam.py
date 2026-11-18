# ruff: noqa: E501  (guide text is kept on one line each)
"""EZO's speaking exam simulator for any practice language (CEFR level estimate).

Three parts, two answers each, decided without a model call:

    Part 1  interview      — short personal questions
    Part 2  description    — describe a place, an event or a situation, one follow-up
    Part 3  discussion     — opinions and reasons on a broader topic

After the sixth answer the session is assessed (CEFR estimate and criteria on EZO's 0–9
scale). It is a simulator, never an official exam or certificate.
"""

from __future__ import annotations

from dataclasses import dataclass

ANSWERS_PER_PART = 2
PARTS = 3

_PART_GUIDE = {
    1: "Part 1 (interview): ask ONE short personal question (home, studies or work, free time, daily routine). Do not repeat earlier questions.",
    2: "Part 2 (description): ask the candidate to describe ONE thing in detail (a place they like, a memorable event, a person, a typical day) and to give reasons; on the second turn ask one follow-up about what they said.",
    3: "Part 3 (discussion): ask ONE broader opinion question connected to Part 2 (society, technology, education, the future) and ask them to explain why; push for reasons and examples.",
}

EXAMINER_GUIDE = (
    "You are EZO's speaking EXAM SIMULATOR (not an official examiner, no certificate). "
    "Be polite, neutral and concise like a real examiner: one question at a time, do not "
    "teach, praise or correct during the exam."
)


@dataclass(slots=True)
class ExamStep:
    part: int
    instruction: str
    finished: bool = False


def advance(meta: dict[str, object], *, learner_answered: bool) -> ExamStep:
    """Move the exam on by one answer (stored in `meta["exam"]["answered"]`)."""
    state = meta.get("exam") if isinstance(meta.get("exam"), dict) else {}
    assert isinstance(state, dict)
    answered = int(state.get("answered", 0) or 0) + (1 if learner_answered else 0)
    meta["exam"] = {"answered": answered}
    if answered >= ANSWERS_PER_PART * PARTS:
        return ExamStep(
            PARTS,
            "The exam is complete. Thank the candidate in one short sentence; the results follow.",
            finished=True,
        )
    part = answered // ANSWERS_PER_PART + 1
    first_of_part = answered % ANSWERS_PER_PART == 0
    intro = ""
    if answered == 0:
        intro = (
            f"Start the exam: in one short line explain it has {PARTS} parts and about "
            f"{ANSWERS_PER_PART * PARTS} questions, and that the candidate can say “tugat” / "
            "“finish” to end early. Then "
        )
    elif first_of_part:
        intro = f"Move to Part {part} with one short transition sentence, then "
    return ExamStep(part, intro + _PART_GUIDE[part])
