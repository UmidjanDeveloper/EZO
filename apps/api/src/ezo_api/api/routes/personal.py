"""Personal Intelligence K9 endpoints: goals, preferences, intelligence profile,
and memory export.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    LanguageGoal,
    LanguageSession,
    LanguageVocabularyItem,
    Memory,
    PersonalGoal,
    User,
)
from ezo_api.schemas.api import MemoryOut, Preferences
from ezo_api.schemas.personal import (
    GoalCategory,
    GoalStatus,
    MemoryConsentUpdate,
    MemoryExportOut,
    PersonalGoalCreate,
    PersonalGoalOut,
    PersonalGoalUpdate,
    PersonalIntelligenceProfile,
)
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/personal", tags=["personal"], dependencies=[Depends(rate_limit("default"))]
)


async def _owned_goal(session: SessionDep, user_id: uuid.UUID, goal_id: uuid.UUID) -> PersonalGoal:
    goal = await session.get(PersonalGoal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(404, detail="Goal not found.")
    return goal


@router.get("/profile", response_model=PersonalIntelligenceProfile)
async def get_personal_profile(
    session: SessionDep, user: CurrentUser
) -> PersonalIntelligenceProfile:
    """Consolidated Personal Intelligence profile: consent, memory counts, goals and progress."""
    prefs = user.preferences or {}
    memory_consent = bool(prefs.get("memory_consent", False))
    auto_memory = bool(prefs.get("auto_memory", False))

    # Memory statistics
    memories = list((await session.scalars(select(Memory).where(Memory.user_id == user.id))).all())
    categories: dict[str, int] = {}
    sensitive_count = 0
    profile_count = 0
    project_count = 0
    for m in memories:
        categories[m.category] = categories.get(m.category, 0) + 1
        if m.sensitive:
            sensitive_count += 1
        if m.memory_type == "profile":
            profile_count += 1
        elif m.memory_type == "project":
            project_count += 1

    memory_stats = {
        "total_count": len(memories),
        "profile_count": profile_count,
        "project_count": project_count,
        "sensitive_count": sensitive_count,
        "categories": categories,
    }

    # Goals statistics
    goals = list(
        (await session.scalars(select(PersonalGoal).where(PersonalGoal.user_id == user.id))).all()
    )
    active_goals = [g for g in goals if g.status == "active"]
    completed_goals = [g for g in goals if g.status == "completed"]
    goals_stats = {
        "total_count": len(goals),
        "active_count": len(active_goals),
        "completed_count": len(completed_goals),
        "average_progress": round(sum(g.progress for g in goals) / len(goals), 2) if goals else 0.0,
    }

    # Learning progress
    speaking_sec = await session.scalar(
        select(func.coalesce(func.sum(LanguageSession.speaking_seconds), 0.0)).where(
            LanguageSession.user_id == user.id
        )
    )
    sessions_count = await session.scalar(
        select(func.count(LanguageSession.id)).where(LanguageSession.user_id == user.id)
    )
    vocab_count = await session.scalar(
        select(func.count(LanguageVocabularyItem.id)).where(
            LanguageVocabularyItem.user_id == user.id
        )
    )
    lang_goals_count = await session.scalar(
        select(func.count(LanguageGoal.id)).where(LanguageGoal.user_id == user.id)
    )

    learning_progress = {
        "total_speaking_seconds": round(float(speaking_sec or 0.0), 1),
        "total_speaking_minutes": round(float(speaking_sec or 0.0) / 60.0, 1),
        "total_sessions": int(sessions_count or 0),
        "vocabulary_items": int(vocab_count or 0),
        "language_goals": int(lang_goals_count or 0),
    }

    return PersonalIntelligenceProfile(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=getattr(user, "role", "user"),
        memory_consent=memory_consent,
        auto_memory=auto_memory,
        preferences=Preferences.model_validate(prefs),
        memory_stats=memory_stats,
        goals_stats=goals_stats,
        learning_progress=learning_progress,
    )


@router.post("/consent")
async def update_memory_consent(
    body: MemoryConsentUpdate, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    """Explicitly grant or revoke consent for memory persistence."""
    current_user = await session.get(User, user.id)
    if current_user is None:
        raise HTTPException(401, detail="User not found.")
    prefs = dict(current_user.preferences or {})
    prefs["memory_consent"] = body.consent
    prefs["auto_memory"] = body.auto_memory if body.consent else False
    current_user.preferences = prefs
    audit(
        session,
        user.id,
        "personal.consent_updated",
        "user",
        user.id,
        {"consent": body.consent, "auto_memory": prefs["auto_memory"]},
    )
    await session.commit()
    return {
        "memory_consent": body.consent,
        "auto_memory": prefs["auto_memory"],
        "message": "Memory consent updated successfully."
        if body.consent
        else "Memory consent revoked. Automatic memory capture is disabled.",
    }


# --- Personal Goals ---


def goal_out(g: PersonalGoal) -> PersonalGoalOut:
    return PersonalGoalOut(
        id=g.id,
        user_id=g.user_id,
        title=g.title,
        description=g.description,
        category=g.category,
        target_date=g.target_date,
        status=g.status,
        progress=g.progress,
        metadata=g.meta or {},
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


@router.get("/goals", response_model=list[PersonalGoalOut])
async def list_goals(
    session: SessionDep,
    user: CurrentUser,
    status: GoalStatus | None = None,
    category: GoalCategory | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PersonalGoalOut]:
    """List goals belonging strictly to the authenticated user."""
    query = select(PersonalGoal).where(PersonalGoal.user_id == user.id)
    if status is not None:
        query = query.where(PersonalGoal.status == status)
    if category is not None:
        query = query.where(PersonalGoal.category == category)
    query = query.order_by(PersonalGoal.created_at.desc()).limit(limit)
    rows = (await session.scalars(query)).all()
    return [goal_out(g) for g in rows]


@router.post("/goals", response_model=PersonalGoalOut, status_code=201)
async def create_goal(
    body: PersonalGoalCreate, session: SessionDep, user: CurrentUser
) -> PersonalGoalOut:
    """Create a new user goal."""
    goal = PersonalGoal(
        user_id=user.id,
        title=body.title.strip(),
        description=body.description.strip(),
        category=body.category,
        target_date=body.target_date,
        progress=body.progress,
        meta=body.metadata,
        status="active",
    )
    session.add(goal)
    await session.flush()
    audit(session, user.id, "personal_goal.create", "goal", goal.id, {"title": goal.title})
    await session.commit()
    return goal_out(goal)


@router.patch("/goals/{goal_id}", response_model=PersonalGoalOut)
async def update_goal(
    goal_id: uuid.UUID, body: PersonalGoalUpdate, session: SessionDep, user: CurrentUser
) -> PersonalGoalOut:
    """Update goal status, title, progress or metadata."""
    goal = await _owned_goal(session, user.id, goal_id)
    if body.title is not None:
        goal.title = body.title.strip()
    if body.description is not None:
        goal.description = body.description.strip()
    if body.category is not None:
        goal.category = body.category
    if body.target_date is not None:
        goal.target_date = body.target_date
    if body.status is not None:
        goal.status = body.status
    if body.progress is not None:
        goal.progress = body.progress
        if goal.progress >= 1.0 and goal.status == "active":
            goal.status = "completed"
    if body.metadata is not None:
        merged = dict(goal.meta or {})
        merged.update(body.metadata)
        goal.meta = merged

    audit(
        session,
        user.id,
        "personal_goal.update",
        "goal",
        goal.id,
        {"fields": sorted(body.model_fields_set)},
    )
    await session.commit()
    return goal_out(goal)


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    """Delete a goal."""
    goal = await _owned_goal(session, user.id, goal_id)
    audit(session, user.id, "personal_goal.delete", "goal", goal.id, {"title": goal.title})
    await session.delete(goal)
    await session.commit()
    return Response(status_code=204)


# --- Memory Export ---


@router.get("/memories/export", response_model=MemoryExportOut)
async def export_memories(session: SessionDep, user: CurrentUser) -> MemoryExportOut:
    """Export all personal memories in JSON and structured Markdown formats."""
    query = (
        select(Memory)
        .where(Memory.user_id == user.id)
        .order_by(Memory.memory_type, Memory.category, Memory.updated_at.desc())
    )
    rows = list((await session.scalars(query)).all())
    memories_out = [MemoryOut.model_validate(m) for m in rows]

    now_iso = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        f"# EZO OS — Shaxsiy Xotira Eksporti ({user.display_name})",
        f"**Sana:** {now_iso}",
        f"**Foydalanuvchi ID:** `{user.id}`",
        f"**Jami xotiralar:** {len(rows)}",
        "",
        "## Xotiralar ro'yxati",
        "| Turi | Kategoriya | Mazmuni | Muhimligi | Manba | So'nggi yangilanish |",
        "|---|---|---|---|---|---|",
    ]
    for m in rows:
        esc_content = m.content.replace("|", "\\|").replace("\n", " ")
        updated_str = m.updated_at.strftime("%Y-%m-%d")
        lines.append(
            f"| {m.memory_type} | {m.category} | {esc_content} | "
            f"{m.importance:.2f} | {m.source} | {updated_str} |"
        )

    lines.append("")
    lines.append("---")
    lines.append(
        "*EZO OS Maxfiylik kafolati: Ushbu ma'lumotlar faqat sizning hisobingizga tegishli.*"
    )
    md_text = "\n".join(lines)

    audit(session, user.id, "personal.memories_exported", "memory", None, {"count": len(rows)})
    await session.commit()

    return MemoryExportOut(
        exported_at=utcnow(),
        user_id=user.id,
        total_memories=len(rows),
        memories=memories_out,
        markdown=md_text,
    )
