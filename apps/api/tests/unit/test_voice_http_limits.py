"""Actual SDK/HTTPX2 request pipeline, controlled network only; no paid API calls."""

import asyncio

import httpx2
import pytest

from ezo_api.voice.base import VoiceError
from ezo_api.voice.openai_audio import OpenAIAudioProvider


class Chunks(httpx2.AsyncByteStream):
    def __init__(self, pieces, delay=0):
        self.pieces, self.delay = pieces, delay
        self.consumed, self.closed = 0, False

    async def __aiter__(self):
        for piece in self.pieces:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.consumed += 1
            yield piece

    async def aclose(self):
        self.closed = True


def configured(handler, **options):
    return OpenAIAudioProvider(
        "voicestudio",
        api_key="ephemeral-test-only",
        base_url="https://voice.invalid/v1",
        stt_model="whisper-1",
        tts_model="tts-1",
        voice="default",
        transport=httpx2.MockTransport(handler),
        timeout=3,
        max_audio=8,
        **options,
    )


@pytest.mark.parametrize("headers,status", [({}, 200), ({}, 500), ({"content-length": "1"}, 200)])
async def test_chunked_oversize_stops_before_full_sdk_buffer_and_closes(headers, status):
    streams = []

    def handler(request):
        body = Chunks([b"1234"] * 20)
        streams.append(body)
        return httpx2.Response(status, headers=headers, stream=body)

    provider = configured(handler)
    try:
        with pytest.raises(VoiceError, match="size limit"):
            await provider.synthesize("Salom", "uz")
        assert streams and all(item.consumed <= 3 and item.closed for item in streams)
    finally:
        await provider._client.close()


@pytest.mark.parametrize(
    "headers",
    [
        {"content-length": "9"},
        {"content-length": "-1"},
        {"content-encoding": "gzip"},
        {"content-encoding": "br"},
    ],
)
async def test_untrusted_headers_are_rejected_before_body_consumption(headers):
    streams = []

    def handler(request):
        body = Chunks([b"sensitive-provider-error"])
        streams.append(body)
        return httpx2.Response(200, headers=headers, stream=body)

    provider = configured(handler)
    try:
        with pytest.raises(VoiceError):
            await provider.synthesize("Salom", "uz")
        assert streams and all(item.consumed == 0 and item.closed for item in streams)
    finally:
        await provider._client.close()


async def test_redirect_never_reaches_another_origin_or_reads_its_body():
    seen = []
    body = Chunks([b"not-read"])

    def handler(request):
        seen.append(str(request.url))
        return httpx2.Response(307, headers={"location": "https://other.invalid"}, stream=body)

    provider = configured(handler)
    try:
        with pytest.raises(VoiceError):
            await provider.synthesize("Salom", "uz")
        assert all(url.startswith("https://voice.invalid/") for url in seen)
        assert body.consumed == 0 and body.closed
    finally:
        await provider._client.close()


async def test_boundary_audio_and_small_real_sdk_transcript_preserve_wire_contract():
    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        if request.url.path.endswith("transcriptions"):
            return httpx2.Response(200, json={"text": "Salom", "language": "uz"})
        return httpx2.Response(200, stream=Chunks([b"ID3a", b"udio"]))

    provider = configured(handler)
    try:
        assert (await provider.synthesize("Salom", "uz")).data == b"ID3audio"
        assert (
            await provider.transcribe(b"voice", "audio/webm", "voice.webm", "uz")
        ).text == "Salom"
    finally:
        await provider._client.close()


async def test_total_deadline_stops_slow_drip_response_and_closes_stream():
    body = Chunks([b"a"] * 100, delay=0.03)
    provider = OpenAIAudioProvider(
        "test",
        api_key="test",
        base_url="https://voice.invalid/v1",
        stt_model="stt",
        tts_model="tts",
        voice="voice",
        timeout=0.08,
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, stream=body)),
    )
    try:
        with pytest.raises(VoiceError) as error:
            await provider.synthesize("Salom", "uz")
        assert error.value.kind == "timeout"
        assert body.closed and body.consumed < 10
    finally:
        await provider._client.close()


async def test_transcript_response_is_bounded_before_json_parse():
    body = Chunks([b'{"text":"', b"x" * 256_000, b'"}'])
    provider = configured(
        lambda request: httpx2.Response(
            200, headers={"content-type": "application/json"}, stream=body
        )
    )
    try:
        with pytest.raises(VoiceError, match="size limit"):
            await provider.transcribe(b"voice", "audio/webm", "voice.webm", "uz")
        assert body.closed and body.consumed < 3
    finally:
        await provider._client.close()


async def test_cancellation_propagates_and_closes_active_sdk_response():
    started = asyncio.Event()

    class Waiting(httpx2.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            started.set()
            await asyncio.sleep(100)
            yield b"not-completed"

        async def aclose(self):
            self.closed = True

    body = Waiting()
    provider = configured(lambda request: httpx2.Response(200, stream=body))
    task = asyncio.create_task(provider.synthesize("Salom", "uz"))
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert body.closed
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await provider._client.close()


@pytest.mark.parametrize(
    "options",
    [
        {"max_audio": 0},
        {"max_audio": 26 * 1024 * 1024},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": 301},
    ],
)
def test_invalid_operator_resource_limits_are_rejected(options):
    with pytest.raises(ValueError, match="resource limits"):
        OpenAIAudioProvider(
            "test", api_key="test", stt_model="stt", tts_model="tts", voice="voice", **options
        )
