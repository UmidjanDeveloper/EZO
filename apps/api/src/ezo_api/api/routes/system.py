"""Health, status, current user, preferences and debug traces."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text

from ezo_api import __version__
from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.api.serializers import user_out
from ezo_api.db.models import AgentRun, User
from ezo_api.maturity import FEATURES
from ezo_api.providers.registry import KNOWN_PROVIDERS
from ezo_api.schemas.api import (
    AgentInfo,
    AgentRunOut,
    FeatureInfo,
    Preferences,
    PreferencesUpdate,
    ProviderStatus,
    SystemStatus,
    UserOut,
)
from ezo_api.security.audit import audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(rate_limit("default"))])


@router.get("/health")
async def health(services: ServicesDep, session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        database = "unreachable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": __version__,
    }


@router.get("/status")
async def status(services: ServicesDep, session: SessionDep, _: CurrentUser) -> SystemStatus:
    router_ = services.router
    providers = [
        ProviderStatus(
            name=name,
            display_name=display,
            configured=name in router_.providers,
            capabilities=sorted(router_.providers[name].capabilities)
            if name in router_.providers
            else [],
        )
        for name, display in KNOWN_PROVIDERS.items()
    ]
    profile = services.personality
    return SystemStatus(
        version=__version__,
        environment=services.settings.environment,
        database="sqlite" if services.settings.is_sqlite else "postgresql",
        offline_mode=router_.is_offline,
        providers=providers,
        routing=router_.describe(),
        agents=[
            AgentInfo(
                key=spec.key,
                names=spec.names,
                description=spec.description,
                available=spec.available,
                maturity=spec.maturity,
                phase=spec.phase,
            )
            for spec in services.agents.catalog()
        ],
        features=[
            FeatureInfo(key=f.key, name=f.name, phase=f.phase, maturity=f.maturity, note=f.note)
            for f in FEATURES
        ],
        personality={
            "name": profile.name,
            "tagline": profile.tagline,
            "traits": list(profile.traits),
            "humor": profile.humor,
            "modes": {k: v.label for k, v in profile.modes.items()},
        },
        debug_traces=services.settings.expose_debug_traces,
    )


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.patch("/me/preferences")
async def update_preferences(
    body: PreferencesUpdate, session: SessionDep, current: CurrentUser
) -> UserOut:
    user = await session.get(User, current.id)
    if user is None:
        raise HTTPException(401, detail="User not found.")
    merged = Preferences.model_validate(user.preferences or {}).model_dump()
    merged.update(body.model_dump(exclude_unset=True, exclude_none=True))
    user.preferences = Preferences.model_validate(merged).model_dump()
    audit(
        session,
        user.id,
        "preferences.update",
        "user",
        user.id,
        {"fields": sorted(body.model_fields_set)},
    )
    await session.commit()
    return user_out(user)


def _require_debug(services: ServicesDep) -> None:
    if not services.settings.expose_debug_traces:
        raise HTTPException(404, detail="Debug traces are disabled (EZO_DEBUG_TRACES=false).")


@router.get("/agent-runs", dependencies=[Depends(_require_debug)])
async def list_runs(
    session: SessionDep,
    user: CurrentUser,
    conversation_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AgentRunOut]:
    query = select(AgentRun).where(AgentRun.user_id == user.id)
    if conversation_id:
        query = query.where(AgentRun.conversation_id == conversation_id)
    query = query.order_by(AgentRun.created_at.desc()).limit(limit)
    return [AgentRunOut.model_validate(r) for r in (await session.scalars(query)).all()]


@router.get("/agent-runs/{run_id}", dependencies=[Depends(_require_debug)])
async def get_run(run_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> AgentRunOut:
    run = await session.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, detail="Run not found.")
    return AgentRunOut.model_validate(run)
