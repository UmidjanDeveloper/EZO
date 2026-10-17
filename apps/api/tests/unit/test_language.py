"""Language Coach logic without a database or model: metrics, modes, IELTS flow, validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ezo_api.db.models import LanguageSession
from ezo_api.language.analysis import describe, lexical_diversity, measure
from ezo_api.language.assessment import MIN_WORDS_FOR_BANDS, validate
from ezo_api.language.ielts import (
    PART1_QUESTIONS_PER_TEST,
    IeltsState,
    advance,
    band_range,
    cue_card,
    new_test,
    round_band,
)
from ezo_api.language.modes import detect_cefr, detect_command, detect_goal, detect_mode
from ezo_api.language.report import build_report

LEARNER = (
    "I live in Tashkent with my family. Um, I am working in a bank since two years. "
    "You know, I like reading books and I goes to the gym every week. "
    "My favourite book is about history because history is interesting and history teaches us."
)


def test_measure_counts_words_fillers_and_repetition() -> None:
    metrics = measure([LEARNER])
    assert metrics.words == 45
    assert metrics.fillers == 2  # "Um", "You know"
    assert metrics.filler_rate == round(100 * 2 / 45, 2)
    assert ("history", 3) in metrics.repeated
    assert metrics.words_per_minute is None  # never invented without measured time
    timed = measure([LEARNER], speech_seconds=23.0)
    assert timed.words_per_minute == round(45 / (23 / 60), 1)
    assert measure([LEARNER], speech_seconds=2.0).words_per_minute is None  # too short to trust
    assert "45 words" in describe(timed) and "words per minute" in describe(timed)


def test_lexical_diversity_uses_a_moving_window() -> None:
    assert lexical_diversity([]) == 0.0
    assert lexical_diversity(["a", "b", "a"]) == round(2 / 3, 3)
    varied = [f"w{i}" for i in range(120)]
    assert lexical_diversity(varied) == 1.0
    assert lexical_diversity(["same"] * 120) == round(1 / 50, 3)


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        ("IELTS speaking qilamiz", "ielts"),
        ("Let's do a mock speaking test", "ielts"),
        ("Job interview practice please", "job_interview"),
        ("Sayohat haqida gaplashamiz, aeroportda", "travel"),
        ("Grammatikamni yaxshilamoqchiman", "grammar"),
        ("Business English for meetings", "business"),
        ("English speaking qilamiz", None),
    ],
)
def test_detect_mode(text: str, mode: str | None) -> None:
    assert detect_mode(text) == mode


def test_detect_cefr_and_goal() -> None:
    assert detect_cefr("B1 darajada gaplashamiz") == "B1"
    assert detect_cefr("I'm a complete beginner") == "A1"
    assert detect_cefr("upper-intermediate please") == "B2"
    assert detect_cefr("hello") is None
    goal = detect_goal("Maqsadim IELTS 7.5 olish")
    assert goal is not None and goal.target_band == 7.5 and goal.cefr is None
    level = detect_goal("My goal is C1 by summer")
    assert level is not None and level.cefr == "C1" and level.target_band is None
    assert detect_goal("Maqsadim kitob o'qish") is None


def test_detect_command_needs_an_active_session_to_finish() -> None:
    assert detect_command("Feedback ber", has_active_session=True) == "finish"
    assert detect_command("Feedback ber", has_active_session=False) == "practice"
    assert detect_command("Grammarim yaxshilandimi?", has_active_session=False) == "progress"
    assert (
        detect_command("Eng ko'p qiladigan 5 ta xatom nima?", has_active_session=True) == "progress"
    )
    assert detect_command("I think travelling is useful", has_active_session=True) == "practice"


def test_ielts_flow_runs_part1_part2_part3_then_finishes() -> None:
    state = new_test("session-1")
    assert state == new_test("session-1")  # deterministic per session
    assert len(state.part1) == PART1_QUESTIONS_PER_TEST
    step = advance(state, learner_answered=False)
    assert step.part == 1 and "not an official test" in step.instruction
    for _ in range(PART1_QUESTIONS_PER_TEST - 1):
        step = advance(state, learner_answered=True)
        assert step.part == 1
    step = advance(state, learner_answered=True)
    card = cue_card(state.cue_card)
    assert step.part == 2 and card.task in step.instruction and "one minute" in step.instruction
    step = advance(state, learner_answered=True)  # long turn
    assert step.part == 2 and card.follow_up in step.instruction
    step = advance(state, learner_answered=True)
    assert step.part == 3 and card.discussion[0] in step.instruction
    for index in (1, 2, 3):
        step = advance(state, learner_answered=True)
        assert card.discussion[index] in step.instruction
    step = advance(state, learner_answered=True)
    assert step.finished and state.finished
    assert IeltsState.from_dict(state.to_dict()) == state


def test_band_rounding_and_ranges() -> None:
    assert round_band(6.24) == 6.0
    assert round_band(6.25) == 6.5
    assert round_band(9.7) == 9.0 and round_band(-1) == 0.0
    assert band_range([6.0, 6.5, 6.0], learner_words=400) == (6.0, 6.5)
    assert band_range([6.0, 6.0, 6.0], learner_words=400) == (6.0, 6.0)
    assert band_range([6.0, 6.0, 6.0], learner_words=100) == (5.5, 6.5)  # little evidence: wider
    with pytest.raises(ValueError):
        band_range([], learner_words=100)


def _model_output(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "fluency_coherence": {"band": 6.3, "evidence": "speaks at length"},
        "lexical_resource": {"band": 5.9, "evidence": "repeats history"},
        "grammatical_range_accuracy": {"band": 5.5, "evidence": "tense errors"},
        "pronunciation": {"band": 6.0, "evidence": "transcript looks clear"},
        "cefr_estimate": "b1",
        "strengths": ["Gives reasons"],
        "weaknesses": ["Tenses"],
        "mistakes": [
            {
                "category": "Verb Tense",
                "original": "I am working in a bank since two years",
                "correction": "I have been working in a bank for two years",
                "explanation": "x",
                "severity": "minor",
            },
            {
                "category": "subject_verb_agreement",
                "original": "I goes to the gym",
                "correction": "I go to the gym",
                "explanation": "y",
                "severity": "major",
            },
            {
                "category": "articles",
                "original": "She buyed a car",  # never said
                "correction": "She bought a car",
                "explanation": "z",
            },
            {
                "category": "made_up",
                "original": "history teaches us",
                "correction": "history teaches us",
                "explanation": "identical",
            },
        ],
        "vocabulary": [{"term": "fascinating", "meaning": "very interesting", "example": "…"}],
        "practice_target": "Present perfect with for/since",
        "summary": "Good start.",
    }
    data.update(overrides)
    return data


def test_validate_rounds_clamps_and_drops_invented_mistakes() -> None:
    result = validate(_model_output(), learner_text=LEARNER, learner_words=300, spoken_share=0.0)
    assert result.scores["fluency_coherence"] == 6.5 and result.scores["lexical_resource"] == 6.0
    assert result.scores["grammatical_range_accuracy"] == 5.5
    assert (result.band_low, result.band_high) == (6.0, 6.0)  # mean of 6.5, 6.0, 5.5
    assert result.cefr_estimate == "B1"
    categories = [m.category for m in result.mistakes]
    assert categories == ["verb_tense", "subject_verb_agreement"]
    assert result.mistakes[1].severity == "major"
    assert (
        result.dropped_mistakes == 2
    )  # the invented one and the "correction" that changes nothing
    # Typed session: pronunciation cannot be judged.
    assert result.scores["pronunciation"] is None
    assert result.pronunciation_confidence == "not_assessed"


def test_validate_pronunciation_is_transcript_assisted_and_not_in_the_range() -> None:
    result = validate(
        _model_output(pronunciation={"band": 9, "evidence": "?"}),
        learner_text=LEARNER,
        learner_words=300,
        spoken_share=1.0,
    )
    assert result.scores["pronunciation"] == 9.0
    assert result.pronunciation_confidence == "transcript_assisted"
    assert (result.band_low, result.band_high) == (6.0, 6.0)  # unchanged by pronunciation
    assert any("transcript-assisted" in note for note in result.notes)


def test_validate_withholds_bands_without_enough_speech_or_model() -> None:
    short = validate(
        _model_output(),
        learner_text=LEARNER,
        learner_words=MIN_WORDS_FOR_BANDS - 1,
        spoken_share=0.0,
    )
    assert short.band_low is None and all(v is None for v in short.scores.values())
    assert short.cefr_estimate is None and "no band is given" in short.notes[0]
    empty = validate(None, learner_text=LEARNER, learner_words=300, spoken_share=0.0)
    assert empty.band_low is None and empty.mistakes == []
    bad = validate(
        _model_output(fluency_coherence={"band": "excellent"}, cefr_estimate="Z9"),
        learner_text=LEARNER,
        learner_words=300,
        spoken_share=0.0,
    )
    assert bad.scores["fluency_coherence"] is None and bad.cefr_estimate is None


def test_report_is_localised_and_honest() -> None:
    session = LanguageSession(mode="ielts", started_at=datetime(2026, 10, 18, tzinfo=UTC))
    assessment = validate(
        _model_output(), learner_text=LEARNER, learner_words=300, spoken_share=0.0
    )
    report = build_report(session, assessment, measure([LEARNER]), "uz")
    assert report.startswith("# IELTS uslubidagi speaking mashg'uloti — 2026-10-18")
    assert "rasmiy IELTS balli emas" in report and "Taxminiy band oralig'i: 6**" in report
    assert "“I goes to the gym” → “I go to the gym”" in report
    assert "baholanmadi" in report  # pronunciation not assessed
    english = build_report(
        session,
        validate(None, learner_text="", learner_words=0, spoken_share=0.0),
        measure([""]),
        "en",
    )
    assert "No band estimate" in english and "not an official IELTS score" in english
