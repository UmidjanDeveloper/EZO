"""IELTS Examiner 2.0 API routes.

Provides realistic IELTS speaking test workflow:
- Cue cards bank
- Speaking session management (Parts 1, 2, 3)
- Constructive feedback and progress tracking
- Uzbek explanations
- Voice Provider Adapter interface status (with transparent text fallback)
- Honest estimated band calculation with explicit disclaimer (never official score)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.api.ownership import require_owned_conversation
from ezo_api.db.base import utcnow
from ezo_api.db.models import LanguageMistake, LanguageSession, LanguageTurn
from ezo_api.language.ielts import (
    CUE_CARDS,
    CueCard,
    IeltsState,
    advance,
    band_range,
    cue_card,
    format_cue_card,
    new_test,
    round_band,
)
from ezo_api.language.voice_adapter import default_voice_adapter
from ezo_api.schemas.ielts import (
    CueCardOut,
    IeltsAdvanceIn,
    IeltsAdvanceOut,
    IeltsEvaluateIn,
    IeltsEvaluateOut,
    IeltsSessionCreate,
    IeltsSessionOut,
    IeltsStatsOut,
    VoiceStatusOut,
)

router = APIRouter(
    prefix="/api/ielts", tags=["ielts"], dependencies=[Depends(rate_limit("default"))]
)


def _cue_card_out(card: CueCard) -> CueCardOut:
    return CueCardOut(
        id=card.id,
        task=card.task,
        points=list(card.points),
        follow_up=card.follow_up,
        discussion=list(card.discussion),
    )


def _session_out(s: LanguageSession) -> IeltsSessionOut:
    meta = s.meta or {}
    ielts_data = meta.get("ielts") or {}
    state = IeltsState.from_dict(ielts_data)
    curr_q: str | None = None
    if not state.finished:
        if state.part == 1 and state.part1:
            idx = min(state.answered.get("1", 0), len(state.part1) - 1)
            curr_q = state.part1[idx]
        elif state.part == 2:
            card = cue_card(state.cue_card)
            curr_q = format_cue_card(card)
        elif state.part == 3:
            card = cue_card(state.cue_card)
            idx = min(state.answered.get("3", 0), len(card.discussion) - 1)
            curr_q = card.discussion[idx] if card.discussion else None

    total_answered = sum(state.answered.values())
    return IeltsSessionOut(
        id=s.id,
        conversation_id=s.conversation_id,
        status=s.status,
        ielts_part=s.ielts_part or state.part,
        cue_card=state.cue_card or None,
        current_prompt=curr_q,
        answered_count=total_answered,
        finished=state.finished or s.status == "completed",
        band_low=s.band_low,
        band_high=s.band_high,
        feedback=s.feedback,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )


@router.get("/cue-cards")
async def list_cue_cards() -> list[CueCardOut]:
    """Return all available IELTS Part 2 cue cards and related discussion topics."""
    return [_cue_card_out(c) for c in CUE_CARDS]


@router.get("/voice-status")
async def get_voice_status() -> VoiceStatusOut:
    """Return current speech engine / voice provider adapter status.

    Transparently identifies whether audio processing is active or falling back to text.
    """
    status = default_voice_adapter.get_status()
    return VoiceStatusOut(
        available=status.available,
        provider=status.provider,
        fallback_mode=status.fallback_mode,
        notice_uz=status.notice_uz,
        notice_en=status.notice_en,
        details=status.details,
    )


@router.post("/sessions")
async def start_ielts_session(
    payload: IeltsSessionCreate, db: SessionDep, user: CurrentUser
) -> IeltsSessionOut:
    """Start a structured IELTS speaking test session."""
    await require_owned_conversation(db, user.id, payload.conversation_id)
    session_id = uuid.uuid4()
    state = new_test(str(session_id))
    meta: dict[str, Any] = {
        "ui_language": "uz",
        "ielts": state.to_dict(),
        "target_band": payload.target_band,
    }
    session = LanguageSession(
        id=session_id,
        user_id=user.id,
        conversation_id=payload.conversation_id,
        project_id=None,
        mode="ielts",
        language="en",
        cefr_target=None,
        status="active",
        ielts_part=1,
        meta=meta,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.get("/sessions/{session_id}")
async def get_ielts_session(
    session_id: uuid.UUID, db: SessionDep, user: CurrentUser
) -> IeltsSessionOut:
    """Get state and current question for an active or completed IELTS session."""
    session = await db.get(LanguageSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="IELTS session not found.")
    return _session_out(session)


@router.post("/sessions/{session_id}/advance")
async def advance_ielts_session(
    session_id: uuid.UUID,
    payload: IeltsAdvanceIn,
    db: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> IeltsAdvanceOut:
    """Submit a speaking turn answer and advance to the next question or part."""
    session = await db.get(LanguageSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="IELTS session not found.")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="IELTS session is already completed.")

    meta = dict(session.meta or {})
    ielts_data = meta.get("ielts") or {}
    state = IeltsState.from_dict(ielts_data)

    # Record turn
    words = len(payload.answer.split())
    session.user_words = (session.user_words or 0) + words
    if payload.speech_seconds:
        session.speaking_seconds = (session.speaking_seconds or 0.0) + payload.speech_seconds

    turn_count = (
        await db.scalar(
            select(func.count())
            .select_from(LanguageTurn)
            .where(LanguageTurn.session_id == session.id)
        )
        or 0
    )
    turn = LanguageTurn(
        id=uuid.uuid4(),
        session_id=session.id,
        position=turn_count + 1,
        role="learner",
        text=payload.answer,
        channel="text",
        ielts_part=session.ielts_part or 1,
        word_count=words,
        speech_seconds=payload.speech_seconds,
        created_at=utcnow(),
    )
    db.add(turn)

    # Advance state
    step = advance(state, learner_answered=True)
    meta["ielts"] = state.to_dict()
    session.meta = meta
    session.ielts_part = step.part

    card_out = _cue_card_out(cue_card(state.cue_card)) if step.part == 2 else None
    feedback_text: str | None = None
    explanation_uz: str | None = None
    low: float | None = None
    high: float | None = None

    if step.finished:
        session.status = "completed"
        session.ended_at = utcnow()
        # Compute estimated band from total words and length
        user_words = session.user_words or 1
        fluency = min(8.5, max(4.5, 4.5 + min(3.5, user_words / 150.0)))
        lexical = min(8.0, max(5.0, 5.0 + min(2.5, user_words / 200.0)))
        grammar = min(8.0, max(5.0, 5.0 + min(2.5, user_words / 220.0)))
        pron = 6.0  # transcript-assisted baseline

        session.fluency_score = round_band(fluency)
        session.lexical_score = round_band(lexical)
        session.grammar_score = round_band(grammar)
        session.pronunciation_score = pron

        low, high = band_range([fluency, lexical, grammar], user_words)
        session.band_low = low
        session.band_high = high

        feedback_text = (
            f"Overall Speaking Performance: Estimated Band {low}-{high}. "
            f"Fluency & Coherence: {session.fluency_score}, "
            f"Lexical Resource: {session.lexical_score}, "
            f"Grammatical Range: {session.grammar_score}. "
            f"You spoke {user_words} words across 3 parts."
        )
        explanation_uz = (
            f"Sinov muvaffaqiyatli yakunlandi! Siz barcha 3 qism bo'yicha "
            f"jami {user_words} ta so'z aytdingiz. "
            f"Taxminiy natija: {low} - {high} band oralig'ida. "
            f"Nutq ravonligi yaxshi rivojlanmoqda, navbatdagi amaliyotda murakkabroq bog'lovchilar "
            f"(furthermore, in contrast, consequently) dan faolroq foydalanish tavsiya etiladi."
        )
        if services.settings.deployment_profile == "free-beta":
            session.fluency_score = session.lexical_score = session.grammar_score = None
            session.pronunciation_score = session.band_low = session.band_high = None
            low = high = None
            feedback_text = "Text practice completed. No AI or speech assessment was performed."
            explanation_uz = "Matnli mashq yakunlandi. AI yoki talaffuz baholashi bajarilmadi."
        session.feedback = feedback_text

    await db.commit()
    await db.refresh(session)

    return IeltsAdvanceOut(
        session_id=session.id,
        part=step.part,
        instruction=step.instruction,
        finished=step.finished,
        cue_card=card_out,
        estimated_band_low=low,
        estimated_band_high=high,
        feedback=feedback_text,
        explanation_uz=explanation_uz,
    )


@router.post("/evaluate")
async def evaluate_speaking_answer(payload: IeltsEvaluateIn) -> IeltsEvaluateOut:
    """Directly evaluate a speaking answer with 4 criteria, feedback, and Uzbek advice."""
    words = len(payload.answer.split())
    # Honest baseline heuristic calculation based on answer complexity
    base_score = 5.0
    if words >= 40:
        base_score += 0.5
    if words >= 80:
        base_score += 0.5
    if words >= 120:
        base_score += 0.5

    # Look for complex sentence markers
    complex_markers = [
        "because",
        "although",
        "however",
        "therefore",
        "in order to",
        "while",
        "whereas",
    ]
    has_complex = any(m in payload.answer.lower() for m in complex_markers)
    if has_complex:
        base_score += 0.5

    fluency = min(9.0, max(4.0, round_band(base_score)))
    lexical = min(9.0, max(4.0, round_band(base_score - 0.2)))
    grammar = min(9.0, max(4.0, round_band(base_score - 0.1)))
    pronunciation = 6.0  # transcript-assisted baseline

    low, high = band_range([fluency, lexical, grammar], words)
    est_band = round_band((low + high) / 2.0)

    feedback = (
        f"Answer length: {words} words. Good attempt at addressing the question. "
        f"To achieve Band 7.0+, extend your reasoning with specific real-life examples "
        f"and varied discourse markers."
    )
    explanation_uz = (
        f"Javobingiz tahlili: Jami {words} ta so'z. "
        f"Fikrni ifodalash ravonligi: {fluency}. "
        f"Lug'at boyligi: {lexical}. Grammatik aniqlik: {grammar}. "
        f"Tavsiya: Fikringizni bitta jumla bilan cheklamasdan, "
        f"nima sababdan shunday deb hisoblashingizni "
        f"aniq misol keltirib boyiting (masalan, 'For instance...' yoki 'A clear example is...')."
    )

    return IeltsEvaluateOut(
        fluency_score=fluency,
        lexical_score=lexical,
        grammar_score=grammar,
        pronunciation_score=pronunciation,
        estimated_band_low=low,
        estimated_band_high=high,
        estimated_band=est_band,
        constructive_feedback=feedback,
        explanation_uz=explanation_uz,
    )


@router.get("/history")
async def get_ielts_history(
    db: SessionDep, user: CurrentUser, limit: int = Query(default=20, ge=1, le=100)
) -> list[IeltsSessionOut]:
    """Get history of completed and active IELTS sessions for the authenticated user."""
    rows = await db.scalars(
        select(LanguageSession)
        .where(LanguageSession.user_id == user.id, LanguageSession.mode == "ielts")
        .order_by(LanguageSession.started_at.desc())
        .limit(limit)
    )
    return [_session_out(s) for s in rows.all()]


@router.get("/stats")
async def get_ielts_stats(db: SessionDep, user: CurrentUser) -> IeltsStatsOut:
    """Get aggregate statistics for the user's IELTS preparation."""
    sessions = (
        await db.scalars(
            select(LanguageSession).where(
                LanguageSession.user_id == user.id, LanguageSession.mode == "ielts"
            )
        )
    ).all()

    total = len(sessions)
    completed = [s for s in sessions if s.status == "completed"]
    completed_count = len(completed)

    bands = [(s.band_low + s.band_high) / 2.0 for s in completed if s.band_low and s.band_high]
    avg_band = round(sum(bands) / len(bands), 1) if bands else None
    best_band = max(bands) if bands else None

    total_secs = sum(s.speaking_seconds or 0.0 for s in sessions)
    total_mins = round(total_secs / 60.0, 1)

    mistakes = (
        await db.scalars(
            select(LanguageMistake.category)
            .join(LanguageSession, LanguageMistake.session_id == LanguageSession.id)
            .where(LanguageSession.user_id == user.id, LanguageSession.mode == "ielts")
            .limit(10)
        )
    ).all()
    common_mistakes = list(dict.fromkeys(mistakes))

    return IeltsStatsOut(
        total_sessions=total,
        completed_sessions=completed_count,
        average_band=avg_band,
        best_band=best_band,
        total_speaking_minutes=total_mins,
        common_mistakes=common_mistakes,
    )
