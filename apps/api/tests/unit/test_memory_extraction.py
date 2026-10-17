import pytest

from ezo_api.memory.extraction import extract_candidates, extract_safe_candidates
from ezo_api.memory.sensitive import sensitive_reason


def test_explicit_remember_strips_trigger_and_categorizes() -> None:
    [candidate] = extract_candidates("Ezo, eslab qol: men minimalist dizaynni yoqtiraman")
    assert candidate.content == "men minimalist dizaynni yoqtiraman"
    assert candidate.explicit
    assert candidate.category == "preference"
    assert candidate.importance >= 0.85


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("I prefer dark mode interfaces.", "preference"),
        ("My name is Aziz.", "personal"),
        ("Меня зовут Анна.", "personal"),
        ("Maqsadim IELTS 7.5 olish.", "goal"),
        ("I struggle with articles in English.", "learning"),
        ("We decided to use PostgreSQL for the project.", "decision"),
    ],
)
def test_pattern_categories(text: str, category: str) -> None:
    [candidate] = extract_candidates(text)
    assert candidate.category == category


def test_ordinary_messages_are_not_memorized() -> None:
    assert extract_candidates("Salom, bugun ob-havo qanday?") == []
    assert extract_candidates("Explain how photosynthesis works.") == []
    assert extract_candidates("Do you remember what I like?") == []  # question


def test_sensitive_content_is_skipped() -> None:
    outcome = extract_safe_candidates("Remember that my password is hunter2.")
    assert outcome.accepted == []
    assert outcome.skipped_sensitive == 1


@pytest.mark.parametrize(
    "text",
    [
        "my card is 4111 1111 1111 1111",
        "pasport raqamim AA1234567",
        "key sk-abcdefghijklmnopqrstuvwx",
        "мой пароль 12345",
    ],
)
def test_sensitive_detection(text: str) -> None:
    assert sensitive_reason(text) is not None


def test_safe_text_is_not_flagged() -> None:
    assert sensitive_reason("I like green tea and long walks") is None
    assert sensitive_reason("Order number 1234567890123") is None  # fails Luhn
