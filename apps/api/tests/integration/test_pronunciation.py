"""Read-aloud pronunciation check (recognition-based, fake speech recognizer)."""

from __future__ import annotations

from ezo_api.language.pronunciation import score_reading
from ezo_api.main import create_app
from ezo_api.voice.service import VoiceService
from tests.conftest import make_settings
from tests.fakes import FakeProvider, FakeVoice

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
SENTENCE = "The weather is beautiful today, so we are going to the park."


def test_perfect_reading_scores_full() -> None:
    result = score_reading(
        SENTENCE, "the weather is beautiful today so we are going to the park", 4000
    )
    assert result.score == 100 and result.to_practise == [] and result.pace == "good"


def test_mistakes_are_marked_per_word() -> None:
    result = score_reading(SENTENCE, "The wether is beautiful today so we going to the bark", 4000)
    marks = {w.word: (w.status, w.heard) for w in result.words}
    assert marks["weather"] == ("close", "wether")
    assert marks["are"] == ("missed", None)
    assert result.to_practise == ["weather", "are", "park"]
    assert 70 <= result.score < 100


def test_wrong_words_extra_words_and_pace() -> None:
    result = score_reading("I like green tea", "I lake green coffee please", 20_000)
    marks = {w.word: w.status for w in result.words}
    assert marks["tea"] == "wrong" and result.extra == ["please"]
    assert result.pace == "slow" and result.score < 70
    cyr = score_reading("Сегодня хорошая погода", "сегодня хорошая погода", 2000)
    assert cyr.score == 100


async def test_pronunciation_endpoint(database_url: str) -> None:
    from httpx import ASGITransport, AsyncClient

    voice = FakeVoice(
        "openai", transcript="The wether is beautiful today so we are going to the park"
    )
    app = create_app(
        make_settings(database_url),
        providers={"anthropic": FakeProvider(name="anthropic")},
        voice=VoiceService([voice], [voice]),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        samples = (await client.get("/api/voice/pronunciation/samples")).json()
        assert SENTENCE in samples["en"]
        response = await client.post(
            "/api/voice/pronunciation",
            files={"audio": ("rec.webm", WEBM)},
            data={"reference": SENTENCE, "language": "en", "duration_ms": "4200"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["to_practise"] == ["weather"] and body["provider"] == "openai"
        assert body["method"].startswith("recognition-based")
        assert voice.calls[-1] == ("stt", len(WEBM), "en")
        bad = await client.post(
            "/api/voice/pronunciation",
            files={"audio": ("rec.webm", WEBM)},
            data={"reference": SENTENCE, "language": "xx"},
        )
        assert bad.status_code == 422
    await app.state.services.db.dispose()
