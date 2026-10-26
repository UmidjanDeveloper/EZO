"""Inspect tool capabilities and calculate explicit percentages, without device control."""

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.db.models import AuditLog, User
from ezo_api.jarvis.device_protocol import SignedDeviceWork, sign_work
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


async def _verified_prerequisites(
    session: Any, user_id: uuid.UUID, services: Any
) -> frozenset[str]:
    """Prerequisites EZO can actually verify for this owner right now."""
    from ezo_api.db.models import JarvisDevice, TelegramRecipient

    verified: set[str] = set()
    devices = (
        await session.scalars(
            select(JarvisDevice).where(
                JarvisDevice.user_id == user_id, JarvisDevice.status == "paired"
            )
        )
    ).all()
    if any(
        d.platform == "windows" and "files.latest_documents" in (d.capabilities or [])
        for d in devices
    ):
        verified.add("paired_windows_companion")
    token = services.settings.telegram_bot_token
    if token is not None and token.get_secret_value():
        verified.add("configured_telegram_integration")
    if await session.scalar(
        select(TelegramRecipient.id).where(
            TelegramRecipient.user_id == user_id, TelegramRecipient.status == "verified"
        )
    ):
        verified.add("verified_telegram_recipient")
    return frozenset(verified)


@router.get("/capabilities")
async def capabilities(
    user: CurrentUser, services: ServicesDep, session: SessionDep
) -> dict[str, Any]:
    verified = await _verified_prerequisites(session, user.id, services)
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
        # Available = every prerequisite verified now. Each task step still needs the
        # owner's on-device consent and, for external effects, a hash-bound approval.
        "device_features": {
            name: availability(frozenset(required), verified)
            for name, required in {
                "windows_downloads": ["paired_windows_companion"],
                "chrome_actions": ["paired_extension", "site_permission"],
                "mobile_actions": ["paired_mobile_companion", "platform_supported_action"],
                "office_pdf": ["reviewed_isolated_conversion_worker"],
                "telegram_send": ["configured_telegram_integration", "verified_telegram_recipient"],
            }.items()
        },
        "trust": "tool_metadata_is_not_action_authorization",
    }


# --- governed tasks, devices and recipients ---------------------------------------------

from datetime import datetime as _datetime  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402

from ezo_api.account.http import enforce_quota  # noqa: E402
from ezo_api.db.models import JarvisDevice, JarvisTask, JarvisTaskStep, TelegramRecipient  # noqa: E402
from ezo_api.jarvis.device_protocol import DeviceWork, SignedDeviceResult  # noqa: E402
from ezo_api.jarvis.service import JarvisError, JarvisService  # noqa: E402


class PairingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    platform: str = Field(pattern=r"^(windows|android|linux|chrome)$")
    public_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    nonce: str = Field(pattern=r"^[a-f0-9]{32,64}$")
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")
    capabilities: list[str] = Field(default_factory=list, max_length=8)


class PairingConfirm(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RecipientIn(BaseModel):
    label: str = Field(min_length=2, max_length=60)


class RecipientVerify(BaseModel):
    code: str = Field(pattern=r"^[a-f0-9]{16}$")


class TaskIn(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    device_id: uuid.UUID | None = None
    language: str = Field(default="uz", pattern=r"^(uz|en|ru)$")


class Decision(BaseModel):
    scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve: bool


def _jarvis_call(exc: JarvisError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


def _iso(value: _datetime | None) -> str | None:
    return value.isoformat() if value else None


def _device_out(device: JarvisDevice) -> dict[str, Any]:
    return {
        "id": str(device.id),
        "name": device.name,
        "platform": device.platform,
        "status": device.status,
        "capabilities": device.capabilities,
        "paired_at": _iso(device.paired_at),
        "last_seen_at": _iso(device.last_seen_at),
    }


def _recipient_out(recipient: TelegramRecipient) -> dict[str, Any]:
    return {
        "id": str(recipient.id),
        "label": recipient.label,
        "status": recipient.status,
        "telegram_name": recipient.telegram_name,
        "verified_at": _iso(recipient.verified_at),
    }


def _step_out(step: JarvisTaskStep) -> dict[str, Any]:
    output = {k: v for k, v in step.output.items() if k not in ("texts",)}
    return {
        "id": str(step.id),
        "position": step.position,
        "action": step.action,
        "state": step.state,
        "output": output,
        "receipt": step.receipt,
        "scope_sha256": step.scope_sha256,
        "error_code": step.error_code,
        "error_message": step.error_message,
    }


async def _task_out(service: JarvisService, task: JarvisTask) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "state": task.state,
        "kind": task.kind,
        "request_text": task.request_text,
        "plan": task.plan,
        "device_id": str(task.device_id) if task.device_id else None,
        "report": task.report,
        "error_code": task.error_code,
        "created_at": _iso(task.created_at),
        "finished_at": _iso(task.finished_at),
        "steps": [_step_out(s) for s in await service.steps(task.id)],
    }


async def _advance_and_commit(service: JarvisService, task: JarvisTask) -> dict[str, Any]:
    await service.advance(task)
    await service.session.commit()
    return await _task_out(service, task)


@router.post("/devices/pairing", status_code=201)
async def request_pairing(
    body: PairingRequest, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    """Called by the companion app; the returned code is displayed ON the device."""
    service = JarvisService(session, services)
    try:
        device, code = await service.request_pairing(user.id, **body.model_dump())
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return {"device": _device_out(device), "code": code, "expires_in_seconds": 600}


@router.post("/devices/{device_id}/confirm")
async def confirm_pairing(
    device_id: uuid.UUID,
    body: PairingConfirm,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    """Called from EZO's own UI by the owner, with the code read from the device screen."""
    service = JarvisService(session, services)
    try:
        device = await service.confirm_pairing(user.id, device_id, body.code)
    except JarvisError as exc:
        await session.commit()  # keep the attempt counter
        raise _jarvis_call(exc) from exc
    await session.commit()
    return _device_out(device)


@router.delete("/devices/{device_id}")
async def revoke_device(
    device_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        device = await service.revoke_device(user.id, device_id)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return _device_out(device)


@router.get("/devices")
async def list_devices(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    return [_device_out(d) for d in await JarvisService(session, services).devices(user.id)]


@router.get("/devices/{device_id}/work")
async def device_work(
    device_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[DeviceWork]:
    service = JarvisService(session, services)
    try:
        work = await service.device_work(user.id, device_id)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return work


@router.post("/devices/{device_id}/results")
async def device_result(
    device_id: uuid.UUID,
    body: SignedDeviceResult,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        task = await service.submit_device_result(user.id, device_id, body)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    return await _advance_and_commit(service, task)


@router.post("/telegram/recipients", status_code=201)
async def add_recipient(
    body: RecipientIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        recipient, code, link = await service.add_recipient(user.id, body.label)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return {"recipient": _recipient_out(recipient), "code": code, "link": link}


@router.post("/telegram/recipients/{recipient_id}/verify")
async def verify_recipient(
    recipient_id: uuid.UUID,
    body: RecipientVerify,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        recipient = await service.verify_recipient(user.id, recipient_id, body.code)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return _recipient_out(recipient)


@router.get("/telegram/recipients")
async def list_recipients(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    return [_recipient_out(r) for r in await JarvisService(session, services).recipients(user.id)]


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskIn, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)

    async def admit() -> None:
        account = await session.get(User, user.id)
        if account is not None:
            await enforce_quota(
                session, account, "jarvis_tasks_per_day", owner_email=services.settings.owner_email
            )

    try:
        task = await service.create_task(user.id, **body.model_dump(), admit=admit)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    return await _advance_and_commit(service, task)


@router.get("/tasks")
async def list_tasks(
    user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[dict[str, Any]]:
    service = JarvisService(session, services)
    return [await _task_out(service, t) for t in await service.tasks(user.id)]


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        task = await service.task(user.id, task_id)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    return await _advance_and_commit(service, task)


@router.post("/tasks/{task_id}/steps/{step_id}/decision")
async def decide(
    task_id: uuid.UUID,
    step_id: uuid.UUID,
    body: Decision,
    user: CurrentUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        task = await service.decide(
            user.id, task_id, step_id, scope_sha256=body.scope_sha256, approve=body.approve
        )
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    return await _advance_and_commit(service, task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        task = await service.cancel(user.id, task_id)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    await session.commit()
    return await _task_out(service, task)


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> dict[str, Any]:
    service = JarvisService(session, services)
    try:
        task = await service.retry(user.id, task_id)
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    return await _advance_and_commit(service, task)


@router.get("/devices/{device_id}/work-signed")
async def signed_device_work(
    device_id: uuid.UUID, user: CurrentUser, session: SessionDep, services: ServicesDep
) -> list[SignedDeviceWork]:
    """Opt-in companion contract; existing clients are never silently upgraded."""
    key = services.settings.jarvis_work_signing_key
    if key is None:
        raise HTTPException(503, detail={"code": "work_signing_not_configured"})
    try:
        work = await JarvisService(session, services).device_work(user.id, device_id)
        # Validate configuration even for an empty queue, without exposing key data.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key.get_secret_value()))
        return [sign_work(item, key.get_secret_value()) for item in work]
    except JarvisError as exc:
        raise _jarvis_call(exc) from exc
    except ValueError:
        raise HTTPException(503, detail={"code": "work_signing_invalid"}) from None
