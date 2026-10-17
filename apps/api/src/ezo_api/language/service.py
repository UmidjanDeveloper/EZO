"""Persistent language practice: sessions, turns, assessments, mistakes, goals and progress."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    LanguageGoal,
    LanguageMetric,
    LanguageMistake,
    LanguageSession,
    LanguageTurn,
    LanguageVocabularyItem,
)
from ezo_api.language.analysis import TextMetrics, measure, words_of
from ezo_api.language.assessment import Assessment
from ezo_api.language.ielts import new_test

PROGRESS_SESSIONS = 10


@dataclass(frozen=True, slots=True)
class RecurringMistake:
    category: str
    count: int
    sessions: int
    example: str


@dataclass(slots=True)
class Progress:
    sessions: list[LanguageSession]
    speaking_minutes: float
    criteria_trend: dict[str, tuple[float, float]] = field(default_factory=dict)
    """criterion → (average of the older half, average of the newer half)."""
    recurring: list[RecurringMistake] = field(default_factory=list)
    goals: list[LanguageGoal] = field(default_factory=list)


async def active_session(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None
) -> LanguageSession | None:
    if conversation_id is None:
        return None
    return await db.scalar(
        select(LanguageSession)
        .where(
            LanguageSession.user_id == user_id,
            LanguageSession.conversation_id == conversation_id,
            LanguageSession.status == "active",
        )
        .order_by(LanguageSession.started_at.desc())
        .limit(1)
    )


async def start_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    mode: str,
    cefr: str | None,
    ui_language: str,
) -> LanguageSession:
    """Start a session; an unfinished one in the same conversation is closed as abandoned."""
    previous = await active_session(db, user_id, conversation_id)
    if previous is not None:
        previous.status = "abandoned"
        previous.ended_at = utcnow()
    meta: dict[str, object] = {"ui_language": ui_language}
    session_id = uuid.uuid4()
    if mode == "ielts":
        meta["ielts"] = new_test(str(session_id)).to_dict()
    language_session = LanguageSession(
        id=session_id,
        user_id=user_id,
        conversation_id=conversation_id,
        project_id=project_id,
        mode=mode,
        language="en",
        cefr_target=cefr,
        status="active",
        ielts_part=1 if mode == "ielts" else None,
        meta=meta,
    )
    db.add(language_session)
    await db.flush()
    return language_session


async def add_turn(
    db: AsyncSession,
    language_session: LanguageSession,
    *,
    role: str,
    text: str,
    channel: str = "text",
    speech_seconds: float | None = None,
) -> LanguageTurn:
    count = await db.scalar(
        select(func.count())
        .select_from(LanguageTurn)
        .where(LanguageTurn.session_id == language_session.id)
    )
    words = len(words_of(text))
    turn = LanguageTurn(
        session_id=language_session.id,
        position=count or 0,
        role=role,
        text=text[:20_000],
        channel=channel,
        ielts_part=language_session.ielts_part,
        word_count=words,
        speech_seconds=speech_seconds if role == "learner" else None,
    )
    db.add(turn)
    if role == "learner":
        language_session.user_words += words
        if speech_seconds:
            language_session.speaking_seconds += speech_seconds
    await db.flush()
    return turn


async def turns_of(db: AsyncSession, language_session: LanguageSession) -> list[LanguageTurn]:
    return list(
        (
            await db.scalars(
                select(LanguageTurn)
                .where(LanguageTurn.session_id == language_session.id)
                .order_by(LanguageTurn.position)
            )
        ).all()
    )


def learner_metrics(turns: list[LanguageTurn]) -> TextMetrics:
    learner = [t for t in turns if t.role == "learner"]
    timed = [t.speech_seconds for t in learner if t.speech_seconds]
    # Words per minute only when every learner turn was timed (otherwise it would be wrong).
    seconds = sum(timed) if learner and len(timed) == len(learner) else None
    return measure([t.text for t in learner], seconds)


def spoken_share(turns: list[LanguageTurn]) -> float:
    learner = [t for t in turns if t.role == "learner"]
    if not learner:
        return 0.0
    return sum(1 for t in learner if t.channel == "voice") / len(learner)


async def save_assessment(
    db: AsyncSession,
    language_session: LanguageSession,
    assessment: Assessment,
    metrics: TextMetrics,
    turns: list[LanguageTurn],
) -> None:
    s = language_session
    s.status = "completed"
    s.ended_at = utcnow()
    s.band_low, s.band_high = assessment.band_low, assessment.band_high
    s.fluency_score = assessment.scores.get("fluency_coherence")
    s.lexical_score = assessment.scores.get("lexical_resource")
    s.grammar_score = assessment.scores.get("grammatical_range_accuracy")
    s.pronunciation_score = assessment.scores.get("pronunciation")
    s.pronunciation_confidence = assessment.pronunciation_confidence
    s.feedback = assessment.summary or None
    s.meta = {
        **(s.meta or {}),
        "cefr_estimate": assessment.cefr_estimate,
        "strengths": assessment.strengths,
        "weaknesses": assessment.weaknesses,
        "practice_target": assessment.practice_target,
        "notes": assessment.notes,
    }

    def metric(name: str, value: float, scale: str, method: str, confidence: str) -> None:
        db.add(
            LanguageMetric(
                user_id=s.user_id,
                session_id=s.id,
                name=name,
                value=value,
                scale=scale,
                method=method,
                confidence=confidence,
            )
        )

    metric("words", metrics.words, "count", "computed", "high")
    metric("lexical_diversity", metrics.lexical_diversity, "ratio", "computed", "high")
    metric("filler_rate", metrics.filler_rate, "per_100_words", "computed", "high")
    if metrics.words_per_minute is not None:
        metric("words_per_minute", metrics.words_per_minute, "wpm", "computed", "medium")
    for key in ("fluency_coherence", "lexical_resource", "grammatical_range_accuracy"):
        value = assessment.scores.get(key)
        if value is not None:
            metric(key, value, "band", "estimated", "medium")
    if assessment.scores.get("pronunciation") is not None:
        metric("pronunciation", assessment.scores["pronunciation"] or 0, "band", "estimated", "low")

    learner_turns = [t for t in turns if t.role == "learner"]
    for mistake in assessment.mistakes:
        needle = normalize(mistake.original)
        turn = next((t for t in learner_turns if needle in normalize(t.text)), None)
        db.add(
            LanguageMistake(
                user_id=s.user_id,
                session_id=s.id,
                turn_id=turn.id if turn else None,
                category=mistake.category,
                original=mistake.original,
                correction=mistake.correction,
                explanation=mistake.explanation,
                severity=mistake.severity,
            )
        )
    for item in assessment.vocabulary:
        term = item["term"].strip().lower()[:120]
        existing = await db.scalar(
            select(LanguageVocabularyItem).where(
                LanguageVocabularyItem.user_id == s.user_id,
                LanguageVocabularyItem.language == s.language,
                LanguageVocabularyItem.term == term,
            )
        )
        if existing is None:
            db.add(
                LanguageVocabularyItem(
                    user_id=s.user_id,
                    language=s.language,
                    term=term,
                    meaning=item["meaning"],
                    example=item["example"],
                    source_session_id=s.id,
                )
            )
        else:
            existing.times_suggested += 1
    await db.flush()


async def recurring_mistakes(
    db: AsyncSession, user_id: uuid.UUID, *, sessions: int = PROGRESS_SESSIONS, limit: int = 5
) -> list[RecurringMistake]:
    """Mistake categories seen across the learner's recent sessions, most frequent first."""
    recent = (
        await db.scalars(
            select(LanguageSession.id)
            .where(LanguageSession.user_id == user_id, LanguageSession.status == "completed")
            .order_by(LanguageSession.started_at.desc())
            .limit(sessions)
        )
    ).all()
    if not recent:
        return []
    rows = (
        await db.scalars(
            select(LanguageMistake)
            .where(LanguageMistake.user_id == user_id, LanguageMistake.session_id.in_(recent))
            .order_by(LanguageMistake.created_at.desc())
        )
    ).all()
    counts = Counter(m.category for m in rows)
    per_session: dict[str, set[uuid.UUID]] = {}
    example: dict[str, str] = {}
    for m in rows:
        per_session.setdefault(m.category, set()).add(m.session_id)
        example.setdefault(m.category, f"“{m.original}” → “{m.correction}”")
    return [
        RecurringMistake(cat, n, len(per_session[cat]), example[cat])
        for cat, n in counts.most_common(limit)
    ]


async def progress(
    db: AsyncSession, user_id: uuid.UUID, limit: int = PROGRESS_SESSIONS
) -> Progress:
    sessions = list(
        (
            await db.scalars(
                select(LanguageSession)
                .where(LanguageSession.user_id == user_id, LanguageSession.status == "completed")
                .order_by(LanguageSession.started_at.desc())
                .limit(limit)
            )
        ).all()
    )
    chronological = list(reversed(sessions))
    trend: dict[str, tuple[float, float]] = {}
    for name, attr in (
        ("fluency_coherence", "fluency_score"),
        ("lexical_resource", "lexical_score"),
        ("grammatical_range_accuracy", "grammar_score"),
    ):
        values = [v for s in chronological if (v := getattr(s, attr)) is not None]
        if len(values) >= 2:
            half = len(values) // 2
            older, newer = values[:half], values[half:]
            trend[name] = (
                round(sum(older) / len(older), 2),
                round(sum(newer) / len(newer), 2),
            )
    goals = list(
        (
            await db.scalars(
                select(LanguageGoal)
                .where(LanguageGoal.user_id == user_id, LanguageGoal.status == "active")
                .order_by(LanguageGoal.created_at.desc())
            )
        ).all()
    )
    return Progress(
        sessions=sessions,
        speaking_minutes=round(sum(s.speaking_seconds for s in sessions) / 60, 1),
        criteria_trend=trend,
        recurring=await recurring_mistakes(db, user_id, sessions=limit),
        goals=goals,
    )


async def set_goal(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    description: str,
    target_band: float | None,
    cefr: str | None,
    deadline: datetime | None = None,
) -> LanguageGoal:
    """One active goal per language: a new goal replaces the previous one (kept as history)."""
    for old in (
        await db.scalars(
            select(LanguageGoal).where(
                LanguageGoal.user_id == user_id,
                LanguageGoal.language == "en",
                LanguageGoal.status == "active",
            )
        )
    ).all():
        old.status = "replaced"
    goal = LanguageGoal(
        user_id=user_id,
        language="en",
        description=description[:300],
        target_band=target_band,
        cefr_target=cefr,
        deadline=deadline,
    )
    db.add(goal)
    await db.flush()
    return goal
