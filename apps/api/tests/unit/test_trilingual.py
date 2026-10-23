"""EZO speaks three languages: detection, transcript language, and TTS steering."""

from __future__ import annotations

from typing import Any

import pytest

from ezo_api.api.routes.voice import heard_language
from ezo_api.core.language import as_language, detect_language
from ezo_api.voice.openai_audio import TTS_INSTRUCTIONS, UZ_TRANSCRIBE_PROMPT, OpenAIAudioProvider
from tests.unit.test_voice import WEBM, FakeAudioClient

# Short, spoken-style turns: the hard cases for a voice assistant.
SPOKEN = [
    ("Salom EZO", "uz"),
    ("Qalaysan?", "uz"),
    ("Ertaga ob-havo qanaqa bo'ladi?", "uz"),
    ("Kalkulyatorni och", "uz"),
    ("Xo'p", "uz"),
    ("Mayli", "uz"),
    ("Toshkentda havo harorati qancha", "uz"),
    ("Men ingliz tilini o‘rganmoqchiman", "uz"),
    ("Салом, қалайсан?", "uz"),
    ("Менга ёрдам бер", "uz"),
    ("Салом, яхшимисиз", "uz"),
    ("Мен уйдаман", "uz"),
    ("Сен кимсан?", "uz"),
    ("Привет, как дела?", "ru"),
    ("Расскажи мне анекдот", "ru"),
    ("Спасибо", "ru"),
    ("Кто ты?", "ru"),
    ("Хорошо", "ru"),
    ("Какая погода завтра в Ташкенте?", "ru"),
    ("Hello", "en"),
    ("Okay", "en"),
    ("Yes", "en"),
    ("Good morning", "en"),
    ("Sure, go ahead", "en"),
    ("What's the weather like tomorrow?", "en"),
    ("Great job", "en"),
    ("Bye", "en"),
]


@pytest.mark.parametrize(("text", "expected"), SPOKEN, ids=[t for t, _ in SPOKEN])
def test_detects_short_spoken_turns(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_no_evidence_falls_back_to_the_hint() -> None:
    assert detect_language("EZO 2026", "ru") == "ru"
    assert detect_language("...", "en") == "en"
    # Ambiguous Cyrillic leans Russian unless the hint says Uzbek.
    assert detect_language("Тошкент", "en") == "ru"
    assert detect_language("Тошкент", "uz") == "uz"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("uzb", "uz"),
        ("Uzbek", "uz"),
        ("russian", "ru"),
        ("en-US", "en"),
        ("rus", "ru"),
        ("turkish", None),
        ("", None),
        (None, None),
    ],
)
def test_provider_language_codes(code: str | None, expected: str | None) -> None:
    assert as_language(code) == expected


def test_heard_language_prefers_provider_then_words() -> None:
    assert heard_language("Привет", "rus", None) == ("ru", "Привет")
    # Whisper labels Uzbek speech "turkish" now and then: the words decide.
    assert heard_language("Qalaysan, yaxshimisan?", "turkish", None)[0] == "uz"
    assert heard_language("How are you?", None, "uz")[0] == "en"
    assert heard_language("2026", None, "ru")[0] == "ru"


def test_uzbek_heard_in_cyrillic_is_shown_in_latin() -> None:
    language, text = heard_language("Салом, қалайсан?", None, None)
    assert language == "uz"
    assert text.startswith("Salom") and "qalaysan" in text
    assert heard_language("Привет", None, None)[1] == "Привет"  # Russian stays Cyrillic


def steerable(client: Any) -> OpenAIAudioProvider:
    return OpenAIAudioProvider(
        "openai",
        api_key="k",
        stt_model="gpt-4o-mini-transcribe",
        tts_model="gpt-4o-mini-tts",
        voice="alloy",
        steerable=True,
        spelling_prompt=True,
        client=client,
    )


@pytest.mark.parametrize("language", ["uz", "en", "ru"])
async def test_tts_is_told_which_language_to_speak(language: str) -> None:
    client = FakeAudioClient()
    await steerable(client).synthesize("Salom", language)
    assert client.calls[0]["instructions"] == TTS_INSTRUCTIONS[language]


async def test_tts_without_language_or_steering_sends_no_instructions() -> None:
    client = FakeAudioClient()
    await steerable(client).synthesize("Salom", None)
    plain = FakeAudioClient()
    await OpenAIAudioProvider(
        "x", api_key="k", stt_model="whisper-1", tts_model="tts-1", voice="alloy", client=plain
    ).synthesize("Salom", "uz")
    assert "instructions" not in client.calls[0] and "instructions" not in plain.calls[0]


async def test_uzbek_transcription_gets_a_latin_spelling_prompt() -> None:
    client = FakeAudioClient()
    p = steerable(client)
    await p.transcribe(WEBM, "audio/webm", "speech.webm", "uz")
    await p.transcribe(WEBM, "audio/webm", "speech.webm", None)  # auto: no bias
    await p.transcribe(WEBM, "audio/webm", "speech.webm", "ru")
    assert client.calls[0]["prompt"] == UZ_TRANSCRIBE_PROMPT
    assert "prompt" not in client.calls[1] and "prompt" not in client.calls[2]
