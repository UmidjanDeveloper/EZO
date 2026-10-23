"""Owner-scoped durable refresh controls; no authority is accepted from source text."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit
from ezo_api.api.routes.document_jobs import _call
from ezo_api.db.models import SourceRefreshPolicy, SourceRefreshRun
from ezo_api.learning.refresh import RefreshQueue, run_out
from ezo_api.learning.refresh_worker import RefreshWorker

router = APIRouter(
    prefix="/api/learning/sources",
    tags=["knowledge-refresh"],
    dependencies=[Depends(rate_limit("default"))],
)


class PermissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    interval_seconds: int | None = Field(default=None, ge=3600, le=2_592_000)
    # An explicit user action, never inferred from registration or document text.
    confirm: bool = False


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID


def queue(services: ServicesDep, *, require_enabled: bool = False) -> RefreshQueue:
    if services.learning is None:
        raise HTTPException(
            503, detail={"code": "learning_off", "message": "Learning is unavailable."}
        )
    if require_enabled and (
        not services.learning.service.enabled or services.settings.deployment_profile == "free-beta"
    ):
        raise HTTPException(
            503, detail={"code": "learning_off", "message": "Learning is turned off."}
        )
    return RefreshQueue(services.db)


@router.put("/{source_id}/refresh-permission")
async def permission(
    source_id: uuid.UUID, body: PermissionIn, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    q = queue(services, require_enabled=body.enabled)
    # Authorize before disclosing confirmation state.
    async with q.transaction(write=False) as session:
        await _call(q.source(session, user.id, source_id))
    if not body.confirm:
        raise HTTPException(
            409,
            detail={
                "code": "confirmation_required",
                "message": "Confirm changing source refresh permission.",
            },
        )
    return await _call(
        q.configure(
            user.id, source_id, enabled=body.enabled, interval_seconds=body.interval_seconds
        )
    )


@router.get("/{source_id}/refresh-permission")
async def permission_status(
    source_id: uuid.UUID, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    q = queue(services)
    async with q.transaction(write=False) as session:
        source = await _call(q.source(session, user.id, source_id))
        policy = await session.scalar(
            select(SourceRefreshPolicy).where(SourceRefreshPolicy.source_id == source.id)
        )
        return {
            "governed": policy is not None,
            "enabled": policy.enabled if policy else False,
            "generation": policy.generation if policy else None,
            "interval_seconds": policy.interval_seconds if policy else None,
            "next_run_at": policy.next_run_at.isoformat()
            if policy and policy.next_run_at
            else None,
            "recurring_consent": bool(policy and policy.enabled and policy.interval_seconds),
        }


@router.post("/{source_id}/refresh-runs", status_code=202)
async def start(
    source_id: uuid.UUID, body: RefreshIn, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    q = queue(services, require_enabled=True)
    result = await _call(q.enqueue(user.id, source_id, body.request_id))
    if services.settings.ingestion_mode == "inline" and result["state"] == "queued":
        assert services.learning is not None
        # Deterministic test/small setup behavior; background production uses the
        # explicit worker command, never one unbounded task per HTTP request.
        await RefreshWorker(q, services.learning.service).process_one()
        async with q.transaction(write=False) as session:
            run = await session.get(SourceRefreshRun, uuid.UUID(result["id"]))
            assert run is not None
            return run_out(run)
    return result


@router.get("/{source_id}/refresh-runs")
async def runs(
    source_id: uuid.UUID,
    user: CurrentUser,
    services: ServicesDep,
    limit: int = Query(20, ge=1, le=20),
    offset: int = Query(0, ge=0, le=100000),
) -> list[dict[str, Any]]:
    q = queue(services)
    async with q.transaction(write=False) as session:
        await _call(q.source(session, user.id, source_id))
        rows = (
            await session.scalars(
                select(SourceRefreshRun)
                .where(SourceRefreshRun.source_id == source_id, SourceRefreshRun.user_id == user.id)
                .order_by(SourceRefreshRun.created_at.desc(), SourceRefreshRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [run_out(row) for row in rows]


@router.post("/{source_id}/refresh-runs/{run_id}/cancel")
async def cancel(
    source_id: uuid.UUID, run_id: uuid.UUID, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    return await _call(queue(services).cancel(user.id, source_id, run_id))


@router.get("/{source_id}/freshness")
async def freshness(
    source_id: uuid.UUID, user: CurrentUser, services: ServicesDep
) -> dict[str, Any]:
    """Observed verification state; never pretend to know an unfetched remote change."""
    q = queue(services)
    async with q.transaction(write=False) as session:
        source = await _call(q.source(session, user.id, source_id))
        policy = await session.scalar(
            select(SourceRefreshPolicy).where(SourceRefreshPolicy.source_id == source.id)
        )
        latest = await session.scalar(
            select(SourceRefreshRun)
            .where(SourceRefreshRun.source_id == source.id)
            .order_by(SourceRefreshRun.created_at.desc(), SourceRefreshRun.id.desc())
            .limit(1)
        )
        now = await q.now(session)
        state = (
            "permission_revoked"
            if policy and not policy.enabled
            else "refresh_in_progress"
            if latest and latest.state in ("queued", "running")
            else "refresh_failed"
            if latest and latest.state == "failed"
            else "check_due"
            if policy and policy.next_run_at and policy.next_run_at <= now
            else "not_indexed"
            if source.indexed_at is None
            else "not_checked"
            if not source.last_checked_at
            else "verified_at_last_check"
        )
        return {
            "state": state,
            "last_checked_at": source.last_checked_at.isoformat()
            if source.last_checked_at
            else None,
            "content_hash": source.content_hash,
            "remote_change_known": False,
            "scope": "last_source_observation",
            "last_indexed_at": source.indexed_at.isoformat() if source.indexed_at else None,
            "latest_run_id": str(latest.id) if latest else None,
        }
