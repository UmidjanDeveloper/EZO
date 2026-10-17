from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from ezo_api.db.models import Message
from ezo_api.main import create_app
from ezo_api.voice.service import VoiceService
from tests.conftest import make_settings
from tests.fakes import FakeProvider, FakeVoice
from tests.integration.helpers import stream_chat

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


async def _app(database_url: str, voice: VoiceService, **env: str) -> tuple[FastAPI, AsyncClient]:
    app = create_app(
        make_settings(database_url, **env),
        providers={
            "anthropic": FakeProvider(name="anthropic", reply="Salom! Qanday yordam beray?")
        },
        voice=voice,
    )
    return app, AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def voice_client(
    database_url: str,
) -> AsyncIterator[tuple[FastAPI, AsyncClient, FakeVoice, FakeVoice]]:
    studio, openai = (
        FakeVoice("voicestudio", fail_kind="unavailable"),
        FakeVoice("openai", transcript="Bugun ob-havo qanday?"),
    )
    app, client = await _app(database_url, VoiceService([studio, openai], [studio, openai]))
    async with client:
        yield app, client, studio, openai
    await app.state.services.db.dispose()


async def test_status_without_providers_says_browser_fallback(client: AsyncClient) -> None:
    status = (await client.get("/api/voice/status")).json()
    assert status == {
        "speech_to_text": [],
        "text_to_speech": [],
        "realtime": False,
        "max_audio_mb": 10,
        "stores_audio": False,
        "browser_fallback": True,
    }
    missing = await client.post("/api/voice/transcribe", files={"audio": ("a.webm", WEBM)})
    assert missing.status_code == 503
    error = missing.json()["error"]
    assert error["code"] == "voice_not_configured" and "VOICESTUDIO_URL" in error["hint"]
    assert (await client.post("/api/voice/speak", json={"text": "Salom"})).status_code == 503


async def test_transcribe_falls_back_and_reports_attempts(voice_client) -> None:  # type: ignore[no-untyped-def]
    _, client, _, openai = voice_client
    status = (await client.get("/api/voice/status")).json()
    assert status["speech_to_text"] == ["voicestudio", "openai"]

    response = await client.post(
        "/api/voice/transcribe", files={"audio": ("rec.webm", WEBM)}, data={"language": "uz"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Bugun ob-havo qanday?" and body["provider"] == "openai"
    assert [(a["provider"], a["ok"]) for a in body["attempts"]] == [
        ("voicestudio", False),
        ("openai", True),
    ]
    assert openai.calls == [("stt", len(WEBM), "uz")]


async def test_audio_is_validated_and_never_stored(voice_client) -> None:  # type: ignore[no-untyped-def]
    app, client, _, _ = voice_client
    not_audio = await client.post(
        "/api/voice/transcribe", files={"audio": ("x.webm", b"%PDF-1.7 not audio")}
    )
    assert not_audio.status_code == 422 and not_audio.json()["error"]["code"] == "bad_audio"

    await client.post("/api/voice/transcribe", files={"audio": ("rec.webm", WEBM)})
    storage = Path(app.state.services.settings.storage_dir)
    assert not any(storage.rglob("*"))  # noqa: ASYNC240 - nothing written to disk
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 0


async def test_oversized_recording_is_rejected(database_url: str) -> None:
    app, client = await _app(
        database_url, VoiceService([FakeVoice("openai")]), EZO_VOICE_MAX_AUDIO_MB="1"
    )
    async with client:
        big = await client.post(
            "/api/voice/transcribe", files={"audio": ("rec.webm", WEBM + b"\x00" * 1024 * 1024)}
        )
        assert big.status_code == 413 and "1 MB" in big.json()["error"]["message"]
    await app.state.services.db.dispose()


async def test_speak_returns_audio_and_falls_back(voice_client) -> None:  # type: ignore[no-untyped-def]
    _, client, _, _ = voice_client
    response = await client.post(
        "/api/voice/speak", json={"text": "Salom, men EZO.", "language": "uz"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["x-ezo-voice-provider"] == "openai"
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"ID3")

    too_long = await client.post("/api/voice/speak", json={"text": "a" * 4001})
    assert too_long.status_code == 422
    bad_language = await client.post("/api/voice/speak", json={"text": "hi", "language": "de"})
    assert bad_language.status_code == 422


async def test_all_providers_failing_is_reported_honestly(database_url: str) -> None:
    failing = VoiceService(
        tts=[
            FakeVoice("voicestudio", fail_kind="timeout"),
            FakeVoice("openai", fail_kind="rate_limit"),
        ]
    )
    app, client = await _app(database_url, failing)
    async with client:
        response = await client.post("/api/voice/speak", json={"text": "Salom"})
        assert response.status_code == 502
        error = response.json()["error"]
        assert error["code"] == "voice_failed" and "browser" in error["hint"]
        assert [a["kind"] for a in error["attempts"]] == ["timeout", "rate_limit"]
    await app.state.services.db.dispose()


async def test_transcript_flows_into_voice_chat(voice_client) -> None:  # type: ignore[no-untyped-def]
    app, client, _, _ = voice_client
    transcript = (
        await client.post("/api/voice/transcribe", files={"audio": ("rec.webm", WEBM)})
    ).json()["text"]
    events = await stream_chat(client, message=transcript, channel="voice")
    done = events[-1][1]["message"]
    assert done["content"] == "Salom! Qanday yordam beray?"
    async with app.state.services.db.sessionmaker() as session:
        user_message = await session.scalar(select(Message).where(Message.role == "user"))
        assert user_message is not None
        assert user_message.content == "Bugun ob-havo qanday?"
        assert user_message.meta["channel"] == "voice"  # transcript stored as text; audio is not
