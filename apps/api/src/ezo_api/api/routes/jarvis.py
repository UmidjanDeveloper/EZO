"""Inspect tool capabilities and calculate explicit percentages, without device control."""

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import AuditLog
from ezo_api.orchestration.planning_policy import availability
from ezo_api.orchestration.tool_plan import PlanInspectionError, ToolGraph, inspect_graph
from ezo_api.tools.percentage import PercentageArgs, calculate_percentages

router = APIRouter(
    prefix="/api/jarvis", tags=["jarvis"], dependencies=[Depends(rate_limit("default"))]
)


@router.post("/inspect-plan")
async def inspect_plan(body: ToolGraph, user: CurrentUser, services: ServicesDep) -> dict[str, Any]:
    try:
        return inspect_graph(body, services.tools, user.id)
    except PlanInspectionError as exc:
        raise HTTPException(422, detail={"code": str(exc)}) from exc


@router.post("/percentages")
async def percentages(
    body: PercentageArgs, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = calculate_percentages(body)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "undefined_percentage", "message": str(exc)}
        ) from exc

    # OpenJarvis-style tool_call trace/outcome adapted to EZO's owner-scoped DB.
    # Unlike the upstream rich collector, no prompts, files or values are stored.
    # This proves a calculation, not document extraction or message delivery.
    def digest(value: dict[str, Any]) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    receipt_id = uuid.uuid4()
    receipt = {
        "schema": "ezo-execution-receipt-v1",
        "step_type": "tool_call",
        "tool": "calculate_percentages",
        "outcome": "completed_deterministic_calculation",
        "input_sha256": digest(body.model_dump(mode="json")),
        "output_sha256": digest(result),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "external_delivery": "not_attempted",
    }
    session.add(
        AuditLog(
            id=receipt_id,
            user_id=user.id,
            action="jarvis.calculation",
            target_type="calculation",
            target_id=str(receipt_id),
            details=receipt,
        )
    )
    await session.commit()
    return {**result, "receipt": {"id": str(receipt_id), **receipt}}


@router.get("/receipts/{receipt_id}")
async def receipt(receipt_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    row = await session.scalar(
        select(AuditLog).where(
            AuditLog.id == receipt_id,
            AuditLog.user_id == user.id,
            AuditLog.action == "jarvis.calculation",
        )
    )
    if row is None:
        raise HTTPException(404, detail="Receipt not found.")
    return {"id": str(row.id), **row.details}


@router.get("/capabilities")
async def capabilities(user: CurrentUser, services: ServicesDep) -> dict[str, Any]:
    # EasyTool-style concise instruction cards from EZO's real code registry.
    # No fetched skill or model can register a tool through this route.
    cards = []
    for name in services.tools.names():
        tool = services.tools.get(name)
        if tool is not None:
            cards.append(
                {
                    **tool.schema(),
                    "requires_confirmation": tool.dangerous,
                    "execution_authorized": False,
                    "timeout_seconds": tool.timeout_seconds,
                }
            )
    return {
        "schema": "ezo-jarvis-capabilities-v1",
        "tools": cards,
        "device_features": {
            name: availability(frozenset(required), frozenset())
            for name, required in {
                "windows_downloads": ["paired_windows_companion", "verified_handle_isolation"],
                "chrome_actions": ["paired_extension", "site_permission"],
                "mobile_actions": ["paired_mobile_companion", "platform_supported_action"],
                "office_pdf": ["reviewed_isolated_conversion_worker"],
                "telegram_send": ["configured_telegram_integration", "scoped_send_approval"],
            }.items()
        },
        "trust": "tool_metadata_is_not_action_authorization",
    }
