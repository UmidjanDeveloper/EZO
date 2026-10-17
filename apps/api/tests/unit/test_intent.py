import pytest

from ezo_api.core.intent import Intent, classify_intent


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Examples from the EZO specification.
        ("Ezo, English speaking qilamiz.", Intent.LANGUAGE_COACH),
        ("Ezo, 15 slide presentation tayyorla.", Intent.PRESENTATION),
        ("Ezo, GitHub projectimdagi bugni top.", Intent.DEVELOPER),
        ("Ezo, oxirgi prezident qarorini tushuntirib ber.", Intent.LEGAL_RESEARCH),
        # More languages and agents.
        ("Let's practice for IELTS speaking part 2", Intent.LANGUAGE_COACH),
        ("Сделай презентацию на 10 слайдов", Intent.PRESENTATION),
        ("Объясни новый указ президента", Intent.LEGAL_RESEARCH),
        ("Bu PDF hujjatni qisqacha mazmunini yoz", Intent.DOCUMENT),
        ("Biznes g'oyamni SWOT tahlil qil", Intent.BUSINESS),
        ("Kompaniyam uchun logotip yaratib ber", Intent.VISUAL),
        ("Ezo, shu PDF asosida taqdimot tayyorla.", Intent.PRESENTATION),
        ("Shu biznes rejamdan investor pitch deck qil", Intent.PRESENTATION),
        ("Shu faylni ingliz tiliga tarjima qil", Intent.DOCUMENT),
        ("Oylik hisobot tayyorla excel jadval bilan", Intent.DOCUMENT),
        ("Bu ikki hujjatni solishtir", Intent.DOCUMENT),
        ("Salom, qalaysan?", Intent.GENERAL),
        ("What should I cook tonight?", Intent.GENERAL),
    ],
)
def test_classify_intent(text: str, expected: Intent) -> None:
    assert classify_intent(text).intent == expected


def test_word_boundaries_prevent_false_matches() -> None:
    # "kodeks" is legal, not code; "kod" must not fire inside it.
    result = classify_intent("Mehnat kodeksi bo'yicha savol")
    assert result.intent == Intent.LEGAL_RESEARCH
    assert "developer" not in result.scores


def test_result_records_signals_and_confidence() -> None:
    result = classify_intent("Ezo, GitHub projectimdagi bugni top.")
    assert result.signals
    assert 0 < result.confidence <= 1
    assert result.scores["developer"] > 0
