"""IELTS Examiner 2.0 API routes.

Provides realistic IELTS speaking test workflow:
- Cue cards bank
- Speaking session management (Parts 1, 2, 3)
- Constructive feedback and progress tracking
- Uzbek explanations
- Voice Provider Adapter interface status (with transparent text fallback)
- Text-only practice with explicit absence of AI/band/pronunciation assessment
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
    cue_card,
    format_cue_card,
    new_test,
)
from ezo_api.language.ielts_feedback import (
    HEURISTIC_NOTICE_EN,
    HEURISTIC_NOTICE_UZ,
    Answer,
    Measured,
    answer_kind,
    measure_group,
)
from ezo_api.language.voice_adapter import default_voice_adapter
from ezo_api.schemas.ielts import (
    AnswerMetricsOut,
    CueCardOut,
    IeltsAdvanceIn,
    IeltsAdvanceOut,
    IeltsEvaluateIn,
    IeltsEvaluateOut,
    IeltsSessionCreate,
    IeltsSessionOut,
    IeltsStatsOut,
    PartMetricsOut,
    SessionMetricsOut,
    TextStatsOut,
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


def _stats(measured: Measured, answers: int) -> dict[str, Any]:
    m = measured.metrics
    return {
        "answers": answers,
        "words": m.words,
        "unique_words": m.unique_words,
        "lexical_diversity": m.lexical_diversity,
        "sentences": m.sentences,
        "words_per_sentence": m.words_per_sentence,
        "fillers": m.fillers,
        "filler_rate": m.filler_rate,
        "repeated": [f"{w} x{n}" for w, n in m.repeated],
        "reported_speech_seconds": m.speech_seconds,
        "words_per_minute": m.words_per_minute,
        "timing_source": measured.timing_source,
    }


def _answer_metrics(answer: Answer) -> AnswerMetricsOut:
    measured = measure_group([answer])
    notes = measured.notes
    return AnswerMetricsOut(
        **_stats(measured, 1),
        part=answer.part,
        answer_kind=answer.kind,
        observations_uz=notes.uz,
        observations_en=notes.en,
        heuristic_notice_uz=HEURISTIC_NOTICE_UZ,
        heuristic_notice_en=HEURISTIC_NOTICE_EN,
    )


def _session_metrics(answers: list[Answer]) -> SessionMetricsOut:
    per_part: list[PartMetricsOut] = []
    for part in (1, 2, 3):
        group = [a for a in answers if a.part == part]
        if not group:
            continue
        measured = measure_group(group)
        notes = measured.notes
        per_part.append(
            PartMetricsOut(
                **_stats(measured, len(group)),
                part=part,
                observations_uz=notes.uz,
                observations_en=notes.en,
            )
        )
    overall = measure_group(answers, with_notes=False)
    return SessionMetricsOut(
        overall=TextStatsOut(**_stats(overall, len(answers))),
        per_part=per_part,
        heuristic_notice_uz=HEURISTIC_NOTICE_UZ,
        heuristic_notice_en=HEURISTIC_NOTICE_EN,
    )


async def _session_answers(db: Any, session_id: uuid.UUID) -> list[Answer]:
    rows = (
        await db.execute(
            select(LanguageTurn.text, LanguageTurn.ielts_part, LanguageTurn.speech_seconds)
            .where(LanguageTurn.session_id == session_id, LanguageTurn.role == "learner")
            .order_by(LanguageTurn.position)
        )
    ).all()
    seen: dict[int, int] = {}
    answers: list[Answer] = []
    for text, part, seconds in rows:
        part = part or 1
        index = seen.get(part, 0)
        seen[part] = index + 1
        answers.append(Answer(text, part, answer_kind(part, index), seconds))
    return answers


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
    try:
        state = new_test(str(session_id), payload.cue_card)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown IELTS cue card.") from exc
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
    # The part (and position in it) this answer belongs to, captured before advance()
    # moves the state on to the next question.
    answered_part = state.part
    answered = Answer(
        payload.answer,
        answered_part,
        answer_kind(answered_part, state.answered.get(str(answered_part), 0)),
        payload.speech_seconds,
    )
    turn = LanguageTurn(
        id=uuid.uuid4(),
        session_id=session.id,
        position=turn_count + 1,
        role="learner",
        text=payload.answer,
        channel="text",
        ielts_part=answered_part,
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
    metrics = _answer_metrics(answered)
    session_metrics: SessionMetricsOut | None = None

    if step.finished:
        session.status = "completed"
        session.ended_at = utcnow()
        # Text length is not an IELTS assessment; audio pronunciation is unobserved.
        session.fluency_score = session.lexical_score = session.grammar_score = None
        session.pronunciation_score = session.band_low = session.band_high = None
        feedback_text = "Text practice completed. No AI or speech assessment was performed."
        explanation_uz = "Matnli mashq yakunlandi. AI yoki talaffuz baholashi bajarilmadi."
        await db.flush()
        session_metrics = _session_metrics(await _session_answers(db, session.id))
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
        metrics=metrics,
        session_metrics=session_metrics,
    )


@router.post("/evaluate")
async def evaluate_speaking_answer(payload: IeltsEvaluateIn) -> IeltsEvaluateOut:
    """Report observable text practice; never invent AI or pronunciation scores."""
    words = len(payload.answer.split())
    # A standalone Part 2 answer is treated as the long turn.
    metrics = _answer_metrics(Answer(payload.answer, payload.part, answer_kind(payload.part, 0)))
    return IeltsEvaluateOut(
        constructive_feedback=(
            f"Answer length: {words} words. No AI assessment was performed. "
            + " ".join(metrics.observations_en)
        ),
        explanation_uz=(
            f"Javobda {words} ta so'z bor. AI va talaffuz baholashi bajarilmagan. "
            + " ".join(metrics.observations_uz)
        ),
        metrics=metrics,
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
