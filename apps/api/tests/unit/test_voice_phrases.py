from ezo_api.voice.phrases import TEST_PHRASES, compare, normalize


def test_phrase_set_covers_the_three_languages_with_short_distinct_phrases() -> None:
    assert set(TEST_PHRASES) == {"uz", "en", "ru"}
    for phrases in TEST_PHRASES.values():
        assert len(phrases) == 5
        assert len(set(phrases)) == 5
        assert all(3 <= len(p.split()) <= 12 for p in phrases)


def test_normalisation_ignores_case_punctuation_and_apostrophe_variants() -> None:
    assert normalize("Salom, EZO!") == "salom ezo"
    assert normalize("qo’y") == normalize("qo'y") == normalize("qoʻy")
    assert normalize("  Hello,   world.  ") == "hello world"


def test_uzbek_cyrillic_transcript_matches_its_latin_reference() -> None:
    result = compare("Rahmat, hozircha shu yetarli.", "Раҳмат, ҳозирча шу етарли.", "uz")
    assert result.exact, result


def test_wer_and_cer_count_real_differences_only() -> None:
    exact = compare(
        "Open the latest file in the Downloads folder.",
        "open the latest file in the downloads folder",
    )
    assert exact.wer == 0.0 and exact.cer == 0.0
    one_wrong = compare("Thank you, that is enough for now.", "Thank you, that is enough for no.")
    assert one_wrong.wer == round(1 / 7, 4)
    assert 0 < one_wrong.cer < 0.1
    missing = compare("Привет EZO, какая сегодня погода?", "какая сегодня погода")
    assert missing.wer == round(2 / 5, 4)
    assert compare("a b c", "").wer == 1.0
