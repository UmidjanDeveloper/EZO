import json

import httpx
import pytest

from ezo_api.settings import Settings
from ezo_api.voice.base import VoiceError
from ezo_api.voice.elevenlabs import ElevenLabsProvider
from ezo_api.voice.service import AllVoiceProvidersFailedError, VoiceService, build_voice_service
from tests.fakes import FakeVoice


def adapter(handler: object, **kwargs: object) -> ElevenLabsProvider:
    values = dict(
        voice_id="reviewed_voice",
        stt_model="scribe_v1",
        tts_model="eleven_multilingual_v2",
        languages=["en", "ru"],
        timeout=1,
        max_audio=128,
        max_text=100,
    )
    values.update(kwargs)
    return ElevenLabsProvider("fixture-secret", transport=httpx.MockTransport(handler), **values)  # type: ignore[arg-type]


async def test_exact_rest_contract_private_headers_and_no_file_retention() -> None:
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.host == "api.elevenlabs.io"
        assert request.headers["xi-api-key"] == "fixture-secret"
        assert "fixture-secret" not in str(request.url)
        if request.url.path == "/v1/speech-to-text":
            assert b'name="file"' in request.content and b"uzb" in request.content
            return httpx.Response(200, json={"text": " Salom dunyo "})
        assert request.url.path == "/v1/text-to-speech/reviewed_voice"
        assert json.loads(request.content)["model_id"] == "eleven_multilingual_v2"
        assert request.url.params["output_format"] == "mp3_44100_128"
        return httpx.Response(200, content=b"ID3audio", headers={"content-type": "audio/mpeg"})

    provider = adapter(handle)
    result = await provider.transcribe(b"RIFFaudio", "audio/wav", "../../private", "uz")
    assert result.text == "Salom dunyo"
    assert (await provider.synthesize("Hello", "en")).data == b"ID3audio"
    assert len(seen) == 2


@pytest.mark.parametrize("status", [301, 307, 401, 403, 429, 500, 503])
async def test_failure_does_not_follow_redirect_or_disclose_body(status: int) -> None:
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status,
            text="fixture-secret private transcript",
            headers={"location": "https://other.invalid"},
        )

    with pytest.raises(VoiceError) as caught:
        await adapter(handle).synthesize("Hello", "en")
    assert len(seen) == 1
    assert "fixture-secret" not in str(caught.value) and "transcript" not in str(caught.value)


async def test_limits_empty_and_unverified_language_reject_before_http() -> None:
    def never(_: httpx.Request) -> httpx.Response:
        pytest.fail("unsafe/unbounded request sent")

    provider = adapter(never)
    for text, lang in [("x" * 101, "en"), ("", "en"), ("Salom", "uz")]:
        with pytest.raises(VoiceError):
            await provider.synthesize(text, lang)
    with pytest.raises(VoiceError):
        await provider.transcribe(b"x" * 129, "audio/wav", "name", "en")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"x" * 129, headers={"content-type": "audio/mpeg"}),
        httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}),
        httpx.Response(200, json={"text": "not audio"}),
    ],
)
async def test_invalid_or_oversized_audio_is_not_accepted(response: httpx.Response) -> None:
    with pytest.raises(VoiceError):
        await adapter(lambda _: response).synthesize("Hello", "en")


def test_stt_only_without_voice_and_secrets_not_in_status_representation() -> None:
    conf = Settings(
        _env_file=None, ELEVENLABS_API_KEY="fixture-secret", EZO_VOICE_PROVIDERS="elevenlabs"
    )  # type: ignore[call-arg]
    voice = build_voice_service(conf)
    assert [p.name for p in voice.stt] == ["elevenlabs"] and voice.tts == []
    assert "fixture-secret" not in repr(conf)


async def test_voice_budget_and_text_limit_cover_fallback_providers() -> None:
    conf = Settings(_env_file=None, EZO_VOICE_CALLS_PER_DAY=1, EZO_VOICE_MAX_TEXT_CHARS=20)  # type: ignore[call-arg]
    service = build_voice_service(conf)
    fake = FakeVoice("fixture")
    service.tts = [fake]
    await service.synthesize("Hello", "en")
    with pytest.raises(AllVoiceProvidersFailedError):
        await service.synthesize("Hello", "en")
    assert len(fake.calls) == 1
    with pytest.raises(AllVoiceProvidersFailedError):
        await service.synthesize("x" * 21, "en")
    assert len(fake.calls) == 1


async def test_trickled_response_has_whole_operation_deadline_and_is_closed() -> None:
    import asyncio

    class SlowBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield b"x"

        async def aclose(self) -> None:
            self.closed = True

    body = SlowBody()
    provider = adapter(
        lambda _: httpx.Response(200, stream=body, headers={"content-type": "audio/mpeg"}),
        timeout=0.03,
    )
    with pytest.raises(VoiceError) as caught:
        await provider.synthesize("Hello", "en")
    assert caught.value.kind == "timeout" and body.closed


# --- Section C: per-language voices and models, ElevenLabs-then-OpenAI ordering ---------


async def test_per_language_voice_and_model_with_fallback_to_the_single_setting() -> None:
    seen: list[tuple[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)["model_id"]))
        return httpx.Response(200, content=b"ID3audio", headers={"content-type": "audio/mpeg"})

    provider = adapter(
        handle,
        languages=["uz", "en", "ru"],
        voice_ids={"uz": "uz_voice", "ru": "ru_voice"},
        tts_models={"uz": "eleven_v3"},
    )
    for lang in ("uz", "en", "ru"):
        assert (await provider.synthesize("Salom", lang)).provider == "elevenlabs"
    assert seen == [
        ("/v1/text-to-speech/uz_voice", "eleven_v3"),
        ("/v1/text-to-speech/reviewed_voice", "eleven_multilingual_v2"),  # en: single settings
        ("/v1/text-to-speech/ru_voice", "eleven_multilingual_v2"),
    ]


def test_supports_language_needs_both_verification_and_a_voice() -> None:
    provider = adapter(lambda _: httpx.Response(500), languages=["en", "ru"], voice_ids={"uz": "v"})
    assert provider.supports_language("en") and provider.supports_language("ru")
    assert not provider.supports_language("uz")  # a voice exists, but "uz" was not verified
    no_default = adapter(
        lambda _: httpx.Response(500), voice_id="", languages=["uz", "en"], voice_ids={"uz": "v"}
    )
    assert no_default.supports_language("uz") and not no_default.supports_language("en")


async def test_service_speaks_uzbek_with_openai_until_elevenlabs_uzbek_is_verified() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, content=b"ID3audio", headers={"content-type": "audio/mpeg"})

    eleven = adapter(handle, languages=["en", "ru"])
    openai = FakeVoice("openai")
    service = VoiceService(tts=[eleven, openai])
    uz = await service.synthesize("Eshitaman seni.", "uz")
    assert uz.value.provider == "openai" and calls == []  # no ElevenLabs HTTP call for Uzbek
    assert [a.provider for a in uz.attempts] == ["elevenlabs", "openai"]
    assert uz.attempts[0].kind == "unavailable"
    en = await service.synthesize("I'm listening.", "en")
    assert en.value.provider == "elevenlabs" and calls == ["/v1/text-to-speech/reviewed_voice"]
    ru = await service.synthesize("Я тебя слушаю.", "ru")
    assert ru.value.provider == "elevenlabs" and len(calls) == 2
    # The owner verified Uzbek: one env var flips it to ElevenLabs.
    verified = adapter(handle, languages=["en", "ru", "uz"], voice_ids={"uz": "uz_voice"})
    assert (
        await VoiceService(tts=[verified, openai]).synthesize("Eshitaman seni.", "uz")
    ).value.provider == "elevenlabs"
    assert calls[-1] == "/v1/text-to-speech/uz_voice"


async def test_service_reports_unavailable_when_no_provider_can_speak_the_language() -> None:
    eleven = adapter(lambda _: httpx.Response(500), languages=["en"])
    with pytest.raises(AllVoiceProvidersFailedError) as caught:
        await VoiceService(tts=[eleven]).synthesize("Salom", "uz")
    assert [a.kind for a in caught.value.attempts] == ["unavailable"]
    with pytest.raises(AllVoiceProvidersFailedError):
        await VoiceService(tts=[]).synthesize("Salom", "uz")


def test_build_voice_service_reads_per_language_settings() -> None:
    conf = Settings(
        _env_file=None,
        ELEVENLABS_API_KEY="fixture-secret",
        EZO_VOICE_PROVIDERS="elevenlabs",
        EZO_ELEVENLABS_VOICE_ID_UZ="uz_voice",
        EZO_ELEVENLABS_TTS_MODEL_UZ="eleven_v3",
        EZO_ELEVENLABS_TTS_LANGUAGES="en,ru,uz",
    )  # type: ignore[call-arg]
    service = build_voice_service(conf)
    assert [p.name for p in service.tts] == ["elevenlabs"]  # a per-language voice is enough
    provider = service.tts[0]
    assert isinstance(provider, ElevenLabsProvider)
    assert provider.voice_for("uz") == "uz_voice" and provider.model_for("uz") == "eleven_v3"
    assert provider.voice_for("en") == "" and not provider.supports_language("en")
    assert "fixture-secret" not in repr(conf)
