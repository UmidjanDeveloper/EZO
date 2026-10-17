from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from ezo_api.settings import Settings
from ezo_api.voice.audio import sniff_audio
from ezo_api.voice.base import VoiceError
from ezo_api.voice.openai_audio import OpenAIAudioProvider
from ezo_api.voice.service import AllVoiceProvidersFailedError, VoiceService, build_voice_service
from tests.fakes import FakeVoice

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 20
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (WEBM, "audio/webm"),
        (b"OggS\x00\x02" + b"\x00" * 20, "audio/ogg"),
        (WAV, "audio/wav"),
        (b"ID3\x04" + b"\x00" * 20, "audio/mpeg"),
        (b"\xff\xfb\x90\x00" + b"\x00" * 20, "audio/mpeg"),
        (b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 16, "audio/mp4"),
    ],
)
def test_sniff_audio_formats(data: bytes, mime: str) -> None:
    kind = sniff_audio(data)
    assert kind is not None and kind.mime_type == mime


def test_sniff_rejects_non_audio() -> None:
    assert sniff_audio(b"%PDF-1.7") is None
    assert sniff_audio(b"MZ\x90\x00") is None
    assert sniff_audio(b"") is None


class FakeAudioClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.audio = SimpleNamespace(
            transcriptions=SimpleNamespace(create=self._transcribe),
            speech=SimpleNamespace(create=self._speak),
        )

    async def _transcribe(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text="  Salom dunyo  ")

    async def _speak(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(content=b"ID3audio")


def provider(client: FakeAudioClient, *, send_language: bool = False) -> OpenAIAudioProvider:
    return OpenAIAudioProvider(
        "test",
        api_key="k",
        stt_model="stt-model",
        tts_model="tts-model",
        voice="alloy",
        send_language_to_tts=send_language,
        client=client,
    )


async def test_openai_audio_transcribe_and_speak() -> None:
    client = FakeAudioClient()
    p = provider(client)
    transcript = await p.transcribe(WEBM, "audio/webm", "speech.webm", "uz")
    assert transcript.text == "Salom dunyo" and transcript.language == "uz"
    assert client.calls[0]["model"] == "stt-model" and client.calls[0]["language"] == "uz"
    assert client.calls[0]["file"] == ("speech.webm", WEBM, "audio/webm")

    audio = await p.synthesize("Salom", "uz")
    assert audio.data == b"ID3audio" and audio.mime_type == "audio/mpeg"
    assert "extra_body" not in client.calls[1]  # OpenAI's API has no language field


async def test_voicestudio_style_sends_language_to_tts() -> None:
    client = FakeAudioClient()
    await provider(client, send_language=True).synthesize("Привет", "ru")
    assert client.calls[0]["extra_body"] == {"language": "ru"}


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (openai.APIConnectionError(request=httpx.Request("POST", "http://x")), "unavailable"),
        (openai.APITimeoutError(request=httpx.Request("POST", "http://x")), "timeout"),
        (
            openai.AuthenticationError(
                "bad key",
                response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
                body=None,
            ),
            "auth",
        ),
        (
            openai.BadRequestError(
                "bad audio",
                response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                body=None,
            ),
            "bad_audio",
        ),
    ],
)
async def test_openai_audio_maps_errors(error: Exception, kind: str) -> None:
    with pytest.raises(VoiceError) as caught:
        await provider(FakeAudioClient(error)).transcribe(WEBM, "audio/webm", "a.webm", None)
    assert caught.value.kind == kind


async def test_service_falls_back_to_next_provider() -> None:
    first, second = FakeVoice("voicestudio", fail_kind="unavailable"), FakeVoice("openai")
    service = VoiceService([first, second], [first, second])
    result = await service.transcribe(WEBM, "audio/webm", "a.webm", "uz")
    assert result.value.provider == "openai"
    assert [(a.provider, a.ok, a.kind) for a in result.attempts] == [
        ("voicestudio", False, "unavailable"),
        ("openai", True, None),
    ]
    spoken = await service.synthesize("Salom", "uz")
    assert spoken.value.provider == "openai"


async def test_service_stops_on_bad_audio_and_reports_all_failures() -> None:
    bad, never = FakeVoice("a", fail_kind="bad_audio"), FakeVoice("b")
    with pytest.raises(AllVoiceProvidersFailedError) as caught:
        await VoiceService([bad, never]).transcribe(WEBM, "audio/webm", "a.webm", None)
    assert [a.provider for a in caught.value.attempts] == ["a"] and never.calls == []

    with pytest.raises(AllVoiceProvidersFailedError) as caught:
        await VoiceService(
            tts=[FakeVoice("a", fail_kind="timeout"), FakeVoice("b", fail_kind="auth")]
        ).synthesize("x", None)
    assert [a.kind for a in caught.value.attempts] == ["timeout", "auth"]


def make(**env: str) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="sqlite:///x.db", **env)  # type: ignore[call-arg]


def test_build_voice_service_order_and_configuration() -> None:
    assert build_voice_service(make(OPENAI_API_KEY="", VOICESTUDIO_URL="")).stt == []

    both = build_voice_service(
        make(OPENAI_API_KEY="sk-x", VOICESTUDIO_URL="http://voicestudio:3900/")
    )
    assert [p.name for p in both.stt] == ["voicestudio", "openai"]
    studio = both.stt[0]
    assert isinstance(studio, OpenAIAudioProvider) and studio.send_language_to_tts

    reordered = build_voice_service(
        make(
            OPENAI_API_KEY="sk-x",
            VOICESTUDIO_URL="http://vs:3900",
            EZO_VOICE_PROVIDERS="openai, voicestudio",
        )
    )
    assert [p.name for p in reordered.tts] == ["openai", "voicestudio"]

    only_openai = build_voice_service(make(OPENAI_API_KEY="sk-x", EZO_VOICE_PROVIDERS="openai"))
    assert [p.name for p in only_openai.stt] == ["openai"]


async def test_voicestudio_wire_format_with_real_sdk() -> None:
    """The exact HTTP requests EZO sends to an OpenAI-compatible voice server (VoiceStudio)."""
    import json

    import httpx2

    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx2.Response(200, json={"text": "Salom"})
        return httpx2.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"})

    client = openai.AsyncOpenAI(
        api_key="vs-key",
        base_url="http://voicestudio:3900/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    studio = OpenAIAudioProvider(
        "voicestudio",
        api_key="vs-key",
        stt_model="whisper-1",
        tts_model="tts-1",
        voice="default",
        send_language_to_tts=True,
        client=client,
    )
    assert (await studio.transcribe(WEBM, "audio/webm", "speech.webm", "uz")).text == "Salom"
    assert (await studio.synthesize("Salom", "uz")).data == b"ID3mp3"

    stt, tts = seen
    assert str(stt.url) == "http://voicestudio:3900/v1/audio/transcriptions"
    assert stt.headers["authorization"] == "Bearer vs-key"
    body = stt.read()
    assert b'name="file"; filename="speech.webm"' in body and b'name="language"' in body
    assert str(tts.url) == "http://voicestudio:3900/v1/audio/speech"
    sent = json.loads(tts.read())
    assert sent == {
        "input": "Salom",
        "model": "tts-1",
        "voice": "default",
        "response_format": "mp3",
        "language": "uz",
    }
