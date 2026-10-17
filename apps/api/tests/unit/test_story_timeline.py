from ezo_api.story.timeline import narration_seconds, plan_timeline


def test_narration_seconds() -> None:
    assert narration_seconds("") == 0.0
    assert narration_seconds("bir ikki uch to'rt besh olti") == round(6 / 2.4 + 0.8, 2)


def test_timeline_is_sequential_and_never_cuts_narration() -> None:
    long_narration = " ".join(["so'z"] * 48)  # ~20.8 s
    slots = plan_timeline([(5.0, ""), (6.0, long_narration), (4.0, "qisqa")])
    assert [(s.start, s.end) for s in slots] == [(0.0, 5.0), (5.0, 25.8), (25.8, 29.8)]


def test_empty_timeline() -> None:
    assert plan_timeline([]) == []
