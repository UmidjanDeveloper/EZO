"""Language Coach data: practice sessions, progress, goals and vocabulary.

Practice itself happens in the normal chat (EZO picks the coach automatically);
these endpoints let the learner look at, and delete, what was recorded.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.db.models import (
    LanguageGoal,
    LanguageMetric,
    LanguageMistake,
    LanguageSession,
    LanguageVocabularyItem,
)
from ezo_api.language import service as lang
from ezo_api.schemas.language import (
    LanguageGoalIn,
    LanguageGoalOut,
    LanguageMetricOut,
    LanguageMistakeOut,
    LanguageProgressOut,
    LanguageSessionDetailOut,
    LanguageSessionOut,
    LanguageTurnOut,
    RecurringMistakeOut,
    VocabularyItemOut,
)
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/language", tags=["language"], dependencies=[Depends(rate_limit("default"))]
)


def session_out(s: LanguageSession) -> LanguageSessionOut:
    meta = s.meta or {}
    return LanguageSessionOut(
        id=s.id,
        mode=s.mode,
        language=s.language,
        status=s.status,
        cefr_target=s.cefr_target,
        cefr_estimate=meta.get("cefr_estimate"),
        ielts_part=s.ielts_part,
        started_at=s.started_at,
        ended_at=s.ended_at,
        speaking_seconds=s.speaking_seconds,
        user_words=s.user_words,
        band_low=s.band_low,
        band_high=s.band_high,
        fluency_score=s.fluency_score,
        lexical_score=s.lexical_score,
        grammar_score=s.grammar_score,
        pronunciation_score=s.pronunciation_score,
        pronunciation_confidence=s.pronunciation_confidence,
        feedback=s.feedback,
        conversation_id=s.conversation_id,
        report_artifact_id=s.report_artifact_id,
    )


def goal_out(g: LanguageGoal) -> LanguageGoalOut:
    return LanguageGoalOut(
        id=g.id,
        description=g.description,
        target_band=g.target_band,
        cefr_target=g.cefr_target,
        deadline=g.deadline,
        status=g.status,
        created_at=g.created_at,
    )


async def _owned(db: SessionDep, user_id: uuid.UUID, session_id: uuid.UUID) -> LanguageSession:
    found = await db.get(LanguageSession, session_id)
    if found is None or found.user_id != user_id:
        raise HTTPException(404, detail="Practice session not found.")
    return found


@router.get("/sessions")
async def list_sessions(
    db: SessionDep, user: CurrentUser, limit: int = Query(default=30, ge=1, le=200)
) -> list[LanguageSessionOut]:
    rows = await db.scalars(
        select(LanguageSession)
        .where(LanguageSession.user_id == user.id)
        .order_by(LanguageSession.started_at.desc())
        .limit(limit)
    )
    return [session_out(s) for s in rows.all()]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID, db: SessionDep, user: CurrentUser
) -> LanguageSessionDetailOut:
    s = await _owned(db, user.id, session_id)
    meta = s.meta or {}
    turns = await lang.turns_of(db, s)
    metrics = (
        await db.scalars(select(LanguageMetric).where(LanguageMetric.session_id == s.id))
    ).all()
    mistakes = (
        await db.scalars(
            select(LanguageMistake)
            .where(LanguageMistake.session_id == s.id)
            .order_by(LanguageMistake.created_at)
        )
    ).all()
    return LanguageSessionDetailOut(
        **session_out(s).model_dump(),
        strengths=list(meta.get("strengths") or []),
        weaknesses=list(meta.get("weaknesses") or []),
        practice_target=str(meta.get("practice_target") or ""),
        notes=list(meta.get("notes") or []),
        turns=[
            LanguageTurnOut(
                position=t.position,
                role=t.role,
                text=t.text,
                channel=t.channel,
                ielts_part=t.ielts_part,
                word_count=t.word_count,
                speech_seconds=t.speech_seconds,
            )
            for t in turns
        ],
        metrics=[
            LanguageMetricOut(
                name=m.name, value=m.value, scale=m.scale, method=m.method, confidence=m.confidence
            )
            for m in metrics
        ],
        mistakes=[
            LanguageMistakeOut(
                category=m.category,
                original=m.original,
                correction=m.correction,
                explanation=m.explanation,
                severity=m.severity,
            )
            for m in mistakes
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: SessionDep,
    user: CurrentUser,
    confirm: bool = Query(default=False),
) -> Response:
    """Delete a practice session with its transcript, metrics and mistakes."""
    if not confirm:
        raise HTTPException(
            409,
            detail={"code": "confirm_required", "message": "Add ?confirm=true to delete."},
        )
    s = await _owned(db, user.id, session_id)
    await db.delete(s)
    audit(db, user.id, "language.session.delete", "language_session", session_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/progress")
async def get_progress(
    db: SessionDep, user: CurrentUser, limit: int = Query(default=10, ge=1, le=50)
) -> LanguageProgressOut:
    progress = await lang.progress(db, user.id, limit=limit)
    return LanguageProgressOut(
        sessions=[session_out(s) for s in progress.sessions],
        speaking_minutes=progress.speaking_minutes,
        criteria_trend={
            name: {"older": older, "newer": newer}
            for name, (older, newer) in progress.criteria_trend.items()
        },
        recurring_mistakes=[
            RecurringMistakeOut(
                category=r.category, count=r.count, sessions=r.sessions, example=r.example
            )
            for r in progress.recurring
        ],
        goals=[goal_out(g) for g in progress.goals],
    )


@router.post("/goals", status_code=201)
async def create_goal(body: LanguageGoalIn, db: SessionDep, user: CurrentUser) -> LanguageGoalOut:
    goal = await lang.set_goal(
        db,
        user.id,
        description=body.description,
        target_band=body.target_band,
        cefr=body.cefr_target,
        deadline=body.deadline,
    )
    audit(db, user.id, "language.goal.set", "language_goal", goal.id)
    await db.commit()
    return goal_out(goal)


@router.get("/vocabulary")
async def list_vocabulary(
    db: SessionDep, user: CurrentUser, limit: int = Query(default=100, ge=1, le=500)
) -> list[VocabularyItemOut]:
    rows = await db.scalars(
        select(LanguageVocabularyItem)
        .where(LanguageVocabularyItem.user_id == user.id)
        .order_by(LanguageVocabularyItem.created_at.desc())
        .limit(limit)
    )
    return [
        VocabularyItemOut(
            term=v.term,
            meaning=v.meaning,
            example=v.example,
            times_suggested=v.times_suggested,
            status=v.status,
            created_at=v.created_at,
        )
        for v in rows.all()
    ]
