"""Server-side speech: transcribe a recording, read text aloud.

Audio is handled in memory only: it is never written to disk, the database or
the logs. Only the text transcript becomes part of the conversation (sent by the
client as a normal chat message).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit
from ezo_api.core.language import DEFAULT_LANGUAGE, Language, as_language, detect_language
from ezo_api.schemas.voice import SpeakIn, TranscriptOut, VoiceAttemptOut, VoiceStatusOut
from ezo_api.translation.translit import detect_script, to_latin
from ezo_api.voice.audio import sniff_audio
from ezo_api.voice.service import AllVoiceProvidersFailedError, VoiceAttempt

router = APIRouter(prefix="/api/voice", tags=["voice"])

NOT_CONFIGURED_HINT = (
    "Add OPENAI_API_KEY or ELEVENLABS_API_KEY (TTS needs EZO_ELEVENLABS_VOICE_ID), "
    "or run VoiceStudio and set VOICESTUDIO_URL. "
    "Until then EZO uses the browser's own speech features."
)


def _attempts(attempts: list[VoiceAttempt]) -> list[VoiceAttemptOut]:
    return [
        VoiceAttemptOut(provider=a.provider, ok=a.ok, kind=a.kind, message=a.message)
        for a in attempts
    ]


def _not_configured(what: str) -> HTTPException:
    return HTTPException(
        503,
        detail={
            "code": "voice_not_configured",
            "message": f"No server {what} provider is configured.",
            "hint": NOT_CONFIGURED_HINT,
        },
    )


def _all_failed(exc: AllVoiceProvidersFailedError) -> HTTPException:
    bad_audio = any(a.kind == "bad_audio" for a in exc.attempts)
    return HTTPException(
        422 if bad_audio else 502,
        detail={
            "code": "bad_audio" if bad_audio else "voice_failed",
            "message": "The recording could not be understood."
            if bad_audio
            else "No voice provider could handle the request.",
            "hint": "EZO will use the browser's speech features instead." if not bad_audio else "",
            "attempts": [a.model_dump() for a in _attempts(exc.attempts)],
        },
    )


def heard_language(
    text: str, reported: str | None, requested: Language | None
) -> tuple[Language, str]:
    """The transcript's language (always uz, en or ru) and its display text.

    A provider's own detection wins when it names one of EZO's languages. Otherwise
    (no detection, or a near miss such as "turkish" for Uzbek speech) the words decide.
    Uzbek heard in Cyrillic is shown in EZO's Latin alphabet.
    """
    language = as_language(reported) or detect_language(text, requested or DEFAULT_LANGUAGE)
    if language == "uz" and detect_script(text) == "cyrillic":
        text = to_latin(text, apostrophe="modifier")
    return language, text


@router.get("/status", dependencies=[Depends(rate_limit("default"))])
async def voice_status(services: ServicesDep, _: CurrentUser) -> VoiceStatusOut:
    voice = services.voice
    return VoiceStatusOut(
        speech_to_text=[p.name for p in voice.stt],
        text_to_speech=[p.name for p in voice.tts],
        realtime=False,
        max_audio_mb=services.settings.voice_max_audio_mb,
        stores_audio=False,
        browser_fallback=True,
    )


@router.post("/transcribe", dependencies=[Depends(rate_limit("chat"))])
async def transcribe(
    services: ServicesDep,
    _: CurrentUser,
    audio: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
    language: Literal["uz", "en", "ru"] | None = Form(default=None),
) -> TranscriptOut:
    if not services.voice.stt:
        raise _not_configured("speech-to-text")
    limit = services.settings.voice_max_audio_mb * 1024 * 1024
    data = await audio.read(limit + 1)
    if len(data) > limit:
        mb = services.settings.voice_max_audio_mb
        raise HTTPException(
            413,
            detail={"code": "too_large", "message": f"The recording is larger than {mb} MB."},
        )
    kind = sniff_audio(data)
    if kind is None:
        raise HTTPException(
            422,
            detail={
                "code": "bad_audio",
                "message": "The upload is not a supported audio recording.",
            },
        )
    try:
        result = await services.voice.transcribe(
            data, kind.mime_type, f"speech.{kind.extension}", language
        )
    except AllVoiceProvidersFailedError as exc:
        raise _all_failed(exc) from exc
    finally:
        del data  # never kept beyond this request
    transcript = result.value
    heard, text = heard_language(transcript.text, transcript.language, language)
    return TranscriptOut(
        text=text,
        language=heard,
        provider=transcript.provider,
        attempts=_attempts(result.attempts),
    )


@router.post("/speak", dependencies=[Depends(rate_limit("chat"))])
async def speak(body: SpeakIn, services: ServicesDep, _: CurrentUser) -> Response:
    if not services.voice.tts:
        raise _not_configured("text-to-speech")
    try:
        result = await services.voice.synthesize(body.text, body.language)
    except AllVoiceProvidersFailedError as exc:
        raise _all_failed(exc) from exc
    audio = result.value
    return Response(
        content=audio.data,
        media_type=audio.mime_type,
        headers={"X-EZO-Voice-Provider": audio.provider, "Cache-Control": "no-store"},
    )
