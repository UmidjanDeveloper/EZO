import pytest

from ezo_api.core.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Salom, bugun qanday ishlar?", "uz"),
        ("Ezo, English speaking qilamiz.", "uz"),
        ("Ezo, 15 slide presentation tayyorla.", "uz"),
        ("Men o‘zbek tilida gaplashaman", "uz"),
        ("Ezo, oxirgi prezident qarorini tushuntirib ber.", "uz"),
        ("Can you help me write an email to my manager?", "en"),
        ("Привет, как дела?", "ru"),
        ("Менга ёрдам беринг, қандай қилиб?", "uz"),  # Uzbek Cyrillic
        ("12345 !!!", "uz"),  # no letters -> fallback
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_fallback_is_configurable() -> None:
    assert detect_language("???", fallback="en") == "en"
