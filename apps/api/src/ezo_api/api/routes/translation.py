"""Translation: text translation, Uzbek Latin ↔ Cyrillic, the glossary, and turn-based
voice interpretation."""

from __future__ import annotations

import base64
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import GlossaryTerm, OrganizationProfile
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.security.audit import audit
from ezo_api.translation import glossary
from ezo_api.translation.interpreter import MODE, TurnBasedInterpreter
from ezo_api.translation.languages import DOMAIN_RULES, LABELS, NAMES, detect
from ezo_api.translation.service import MAX_TEXT_CHARS, TranslationError, translate_text
from ezo_api.translation.translit import detect_script, transliterate
from ezo_api.voice.audio import sniff_audio
from ezo_api.voice.service import AllVoiceProvidersFailedError

router = APIRouter(prefix="/api/translation", tags=["translation"])

LanguageCode = Literal["uz", "uz-cyrl", "ru", "en"]
GlossaryLanguage = Literal["uz", "ru", "en"]
DomainName = Literal["general", "official", "academic", "business", "technical", "legal"]


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    target: LanguageCode
    source: LanguageCode | None = None
    domain: DomainName = "general"
    use_glossary: bool = True
    organization_id: uuid.UUID | None = None


class TranslateOut(BaseModel):
    text: str
    source_language: str
    target_language: str
    method: str
    quality: dict[str, Any]
    warnings: list[str]
    terms: list[dict[str, str]]
    provider: str | None
    model: str | None


class TransliterateIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    to: Literal["latin", "cyrillic"]
    apostrophe: Literal["ascii", "modifier"] = "ascii"


class GlossaryIn(BaseModel):
    source_language: GlossaryLanguage
    target_language: GlossaryLanguage
    source_term: str = Field(min_length=1, max_length=300)
    target_term: str = Field(min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=500)
    organization_id: uuid.UUID | None = None


class GlossaryOut(GlossaryIn):
    id: uuid.UUID

    model_config = {"from_attributes": True}


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


async def _organization(
    session: SessionDep, user_id: uuid.UUID, org_id: uuid.UUID | None
) -> uuid.UUID | None:
    if org_id is None:
        return None
    org = await session.get(OrganizationProfile, org_id)
    if org is None or org.user_id != user_id:
        raise _fail(404, "not_found", "Organization profile not found.")
    return org_id


@router.get("/languages", dependencies=[Depends(rate_limit("default"))])
async def languages(_: CurrentUser) -> dict[str, Any]:
    return {
        "languages": [{"code": c, "name": NAMES[c], "label": LABELS[c]} for c in NAMES],
        "domains": list(DOMAIN_RULES),
        "max_text_chars": MAX_TEXT_CHARS,
        "interpretation": MODE,
    }


@router.post("/transliterate", dependencies=[Depends(rate_limit("default"))])
async def transliterate_text(body: TransliterateIn, _: CurrentUser) -> dict[str, Any]:
    """Uzbek Latin ↔ Cyrillic by fixed rules (no model, no cost)."""
    return {
        "text": transliterate(body.text, body.to, apostrophe=body.apostrophe),
        "from_script": detect_script(body.text),
        "to": body.to,
        "engine": "rules",
    }


@router.post("/translate", dependencies=[Depends(rate_limit("chat"))])
async def translate(
    body: TranslateIn, services: ServicesDep, session: SessionDep, user: CurrentUser
) -> TranslateOut:
    source = body.source or detect(body.text)
    if source == body.target:
        raise _fail(422, "same_language", "The text is already in the target language.")
    org_id = await _organization(session, user.id, body.organization_id)
    terms = (
        await glossary.load_terms(session, user.id, source, body.target, org_id)
        if body.use_glossary
        else []
    )
    try:
        result = await translate_text(
            services.router,
            body.text,
            source=source,
            target=body.target,
            domain=body.domain,
            terms=terms,
        )
    except TranslationError as exc:
        status = {"offline": 503, "too_long": 413, "same_language": 422}.get(exc.code, 502)
        raise _fail(status, exc.code, exc.message) from exc
    except (AllProvidersFailedError, StreamInterruptedError) as exc:
        raise _fail(502, "provider_failed", "The AI provider failed; try again.") from exc
    audit(
        session,
        user.id,
        "translation.text",
        "translation",
        None,
        {"source": source, "target": body.target, "chars": len(body.text), "method": result.method},
    )
    await session.commit()
    return TranslateOut(
        text=result.text,
        source_language=result.source_language,
        target_language=result.target_language,
        method=result.method,
        quality=result.quality.summary(),
        warnings=result.quality.lines(),
        terms=[{"source": t.source, "target": t.target} for t in result.terms],
        provider=result.provider,
        model=result.model,
    )


@router.post("/interpret", dependencies=[Depends(rate_limit("chat"))])
async def interpret(
    services: ServicesDep,
    session: SessionDep,
    user: CurrentUser,
    audio: UploadFile = File(...),  # noqa: B008 (FastAPI dependency declaration)
    target: LanguageCode = Form(...),  # noqa: B008
    source: LanguageCode | None = Form(default=None),  # noqa: B008
    speak: bool = Form(default=True),
) -> dict[str, Any]:
    """One interpreted turn: the recording is transcribed, translated and (if a speech
    provider is configured and `speak` is set) read aloud. Turn-based, not simultaneous."""
    if not services.voice.stt:
        raise _fail(503, "voice_not_configured", "No speech-to-text provider is configured.")
    if services.router.is_offline:
        raise _fail(503, "offline", "Translation needs a connected AI provider.")
    limit = services.settings.voice_max_audio_mb * 1024 * 1024
    data = await audio.read(limit + 1)
    if len(data) > limit:
        raise _fail(413, "too_large", "The recording is too large.")
    kind = sniff_audio(data)
    if kind is None:
        raise _fail(422, "bad_audio", "The upload is not a supported audio recording.")

    async def terms_for(spoken: str, into: str) -> list[glossary.Term]:
        return await glossary.load_terms(session, user.id, spoken, into, None)

    try:
        turn = await TurnBasedInterpreter(services.voice, services.router).interpret(
            data,
            mime_type=kind.mime_type,
            filename=f"speech.{kind.extension}",
            source=source,
            target=target,
            terms_for=terms_for,
            speak=speak,
        )
    except AllVoiceProvidersFailedError as exc:
        raise _fail(502, "voice_failed", "No voice provider could handle the recording.") from exc
    except TranslationError as exc:
        raise _fail(422 if exc.code == "same_language" else 502, exc.code, exc.message) from exc
    except (AllProvidersFailedError, StreamInterruptedError) as exc:
        raise _fail(502, "provider_failed", "The AI provider failed; try again.") from exc
    finally:
        del data  # audio is never kept beyond this request
    translation = turn.translation
    return {
        "mode": turn.mode,
        "transcript": turn.transcript.text,
        "source_language": translation.source_language,
        "target_language": translation.target_language,
        "translation": translation.text,
        "warnings": translation.quality.lines(),
        "audio_base64": base64.b64encode(turn.speech.data).decode() if turn.speech else None,
        "audio_mime": turn.speech.mime_type if turn.speech else None,
    }


@router.get("/glossary", dependencies=[Depends(rate_limit("default"))])
async def list_glossary(
    session: SessionDep,
    user: CurrentUser,
    source_language: GlossaryLanguage | None = None,
    target_language: GlossaryLanguage | None = None,
) -> list[GlossaryOut]:
    query = select(GlossaryTerm).where(GlossaryTerm.user_id == user.id)
    if source_language:
        query = query.where(GlossaryTerm.source_language == source_language)
    if target_language:
        query = query.where(GlossaryTerm.target_language == target_language)
    rows = (await session.scalars(query.order_by(GlossaryTerm.source_term).limit(2_000))).all()
    return [GlossaryOut.model_validate(r) for r in rows]


def _clean(body: GlossaryIn) -> dict[str, Any]:
    if body.source_language == body.target_language:
        raise _fail(422, "same_language", "Source and target languages must differ.")
    data = body.model_dump()
    data["source_term"] = body.source_term.strip()
    data["target_term"] = body.target_term.strip()
    data["note"] = (body.note or "").strip() or None
    if not data["source_term"] or not data["target_term"]:
        raise _fail(422, "empty_term", "Both terms are required.")
    return data


@router.post("/glossary", status_code=201, dependencies=[Depends(rate_limit("default"))])
async def create_term(body: GlossaryIn, session: SessionDep, user: CurrentUser) -> GlossaryOut:
    data = _clean(body)
    await _organization(session, user.id, body.organization_id)
    term = GlossaryTerm(user_id=user.id, **data)
    session.add(term)
    await session.flush()
    audit(session, user.id, "glossary.create", "glossary_term", term.id, {})
    await session.commit()
    return GlossaryOut.model_validate(term)


async def _owned(session: SessionDep, user_id: uuid.UUID, term_id: uuid.UUID) -> GlossaryTerm:
    term = await session.get(GlossaryTerm, term_id)
    if term is None or term.user_id != user_id:
        raise _fail(404, "not_found", "Glossary term not found.")
    return term


@router.put("/glossary/{term_id}", dependencies=[Depends(rate_limit("default"))])
async def update_term(
    term_id: uuid.UUID, body: GlossaryIn, session: SessionDep, user: CurrentUser
) -> GlossaryOut:
    term = await _owned(session, user.id, term_id)
    data = _clean(body)
    await _organization(session, user.id, body.organization_id)
    for key, value in data.items():
        setattr(term, key, value)
    audit(session, user.id, "glossary.update", "glossary_term", term.id, {})
    await session.commit()
    await session.refresh(term)
    return GlossaryOut.model_validate(term)


@router.delete(
    "/glossary/{term_id}", status_code=204, dependencies=[Depends(rate_limit("default"))]
)
async def delete_term(term_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    term = await _owned(session, user.id, term_id)
    await session.delete(term)
    audit(session, user.id, "glossary.delete", "glossary_term", term_id, {})
    await session.commit()
    return Response(status_code=204)
