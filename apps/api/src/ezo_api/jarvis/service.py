"""JARVIS governed task engine: durable tasks, paired devices, approvals, receipts.

Flow (owner's reference scenario):

    request text ──planner──▶ validated plan ──▶ durable task + fixed steps
      1 files.latest_documents   on the paired device (signed result, authorised folder)
      2 document.extract          text of both files (isolated worker for PDF/DOCX/XLSX)
      3 compute.percentages       exact decimal comparison with the previous file
      4 document.convert_pdf      newest file as PDF (isolated worker for Office files)
      5 document.report_pdf       percentage report PDF (EZO's own renderer)
      6 telegram.send             AFTER the owner approves the exact recipient+files hash

Every external effect (step 6) waits in ``awaiting_authorization`` for an approval bound
to ``scope_sha256``. A step only becomes ``completed`` with real evidence: a verified
device signature, produced bytes, or Telegram's own ``message_id``. Nothing in this
module takes instructions from file contents or model output.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    AuditLog,
    JarvisAuthorization,
    JarvisDevice,
    JarvisTask,
    JarvisTaskStep,
    TelegramRecipient,
)
from ezo_api.jarvis import percentages
from ezo_api.jarvis.device_protocol import (
    DEVICE_EXTENSIONS,
    DeviceWork,
    SignedDeviceResult,
    verify_pairing,
    verify_result,
)
from ezo_api.jarvis.planner import DocumentWorkflowPlan, PlanError, plan_document_workflow
from ezo_api.jarvis.telegram import TelegramClient, TelegramError

PAIRING_CODE_TTL = timedelta(minutes=10)
LINK_CODE_TTL = timedelta(minutes=30)
DEVICE_WORK_TTL = timedelta(minutes=5)
MAX_CONFIRM_ATTEMPTS = 5
MAX_OPEN_TASKS = 10
TEXT_FORMATS = ("txt", "csv")
OFFICE_FORMATS = ("docx", "xlsx", "pptx")
# A failed step may be re-run only when re-running cannot duplicate an external effect.
RETRY_SAFE_ACTIONS = frozenset(
    {
        "files.latest_documents",
        "document.extract",
        "compute.percentages",
        "document.convert_pdf",
        "document.report_pdf",
    }
)

Extractor = Callable[[bytes, str], Awaitable[str]]
"""Text of an untrusted document; runs only in the isolated document worker."""
Converter = Callable[[bytes, str], Awaitable[bytes]]
"""Office file → PDF; runs only in the isolated document worker."""


class JarvisError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@dataclass(slots=True)
class Workers:
    """Capabilities this process has. The API process has none of the native ones."""

    extractor: Extractor | None = None
    converter: Converter | None = None
    telegram: TelegramClient | None = None


class JarvisService:
    def __init__(self, session: AsyncSession, services: Any, workers: Workers | None = None):
        self.session = session
        self.services = services
        self.workers = workers or Workers()

    # ------------------------------------------------------------------ audit

    def _audit(self, user_id: uuid.UUID, action: str, target: Any, details: dict[str, Any]) -> None:
        self.session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                target_type="jarvis",
                target_id=str(target),
                details=details,
            )
        )

    # ------------------------------------------------------------------ devices

    async def request_pairing(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        platform: str,
        public_key: str,
        nonce: str,
        signature: str,
        capabilities: list[str],
    ) -> tuple[JarvisDevice, str]:
        """A device proves possession of its key; the returned code is shown ON the device
        and must be typed by the owner into EZO to finish pairing."""
        try:
            verify_pairing(public_key, signature, name, platform, nonce)
        except ValueError as exc:
            raise JarvisError(
                "invalid_signature", "The pairing signature is invalid.", 422
            ) from exc
        if await self.session.scalar(
            select(JarvisDevice.id).where(JarvisDevice.public_key == public_key)
        ):
            raise JarvisError("key_in_use", "This device key is already registered.")
        code = _code()
        device = JarvisDevice(
            user_id=user_id,
            name=name,
            platform=platform,
            public_key=public_key,
            status="pending",
            code_sha256=_hash_code(code),
            code_expires_at=utcnow() + PAIRING_CODE_TTL,
            capabilities=[c for c in capabilities if c in ("files.latest_documents",)],
        )
        self.session.add(device)
        await self.session.flush()
        self._audit(user_id, "jarvis.device.pairing_requested", device.id, {"platform": platform})
        return device, code

    async def confirm_pairing(
        self, user_id: uuid.UUID, device_id: uuid.UUID, code: str
    ) -> JarvisDevice:
        device = await self._device(user_id, device_id, lock=True)
        if device.status != "pending":
            raise JarvisError("not_pending", "This device is not waiting for pairing.")
        if device.code_expires_at is None or device.code_expires_at < utcnow():
            raise JarvisError("code_expired", "The pairing code expired; pair again.")
        if device.confirm_attempts >= MAX_CONFIRM_ATTEMPTS:
            raise JarvisError("too_many_attempts", "Too many wrong codes; pair again.", 429)
        device.confirm_attempts += 1
        if not secrets.compare_digest(device.code_sha256 or "", _hash_code(code.strip())):
            await self.session.flush()
            raise JarvisError("wrong_code", "The code does not match the one on the device.", 422)
        device.status, device.paired_at = "paired", utcnow()
        device.code_sha256 = device.code_expires_at = None
        self._audit(user_id, "jarvis.device.paired", device.id, {"platform": device.platform})
        return device

    async def revoke_device(self, user_id: uuid.UUID, device_id: uuid.UUID) -> JarvisDevice:
        device = await self._device(user_id, device_id, lock=True)
        device.status, device.revoked_at = "revoked", utcnow()
        # Work already handed to the device can no longer be accepted.
        steps = (
            await self.session.scalars(
                select(JarvisTaskStep)
                .join(JarvisTask, JarvisTask.id == JarvisTaskStep.task_id)
                .where(JarvisTask.device_id == device.id, JarvisTaskStep.state == "awaiting_device")
            )
        ).all()
        for step in steps:
            await self._fail(step, "device_revoked", "The device was revoked.")
        self._audit(user_id, "jarvis.device.revoked", device.id, {})
        return device

    async def devices(self, user_id: uuid.UUID) -> list[JarvisDevice]:
        return list(
            (
                await self.session.scalars(
                    select(JarvisDevice)
                    .where(JarvisDevice.user_id == user_id)
                    .order_by(JarvisDevice.created_at.desc())
                )
            ).all()
        )

    async def _device(
        self, user_id: uuid.UUID, device_id: uuid.UUID, *, lock: bool = False
    ) -> JarvisDevice:
        query = select(JarvisDevice).where(
            JarvisDevice.id == device_id, JarvisDevice.user_id == user_id
        )
        device = await self.session.scalar(query.with_for_update() if lock else query)
        if device is None:
            raise JarvisError("not_found", "Device not found.", 404)
        return device

    # ------------------------------------------------------------------ recipients

    async def add_recipient(
        self, user_id: uuid.UUID, label: str
    ) -> tuple[TelegramRecipient, str, str]:
        telegram = self._telegram()
        label = label.strip()
        existing = await self.session.scalar(
            select(TelegramRecipient).where(
                TelegramRecipient.user_id == user_id,
                func.lower(TelegramRecipient.label) == label.lower(),
            )
        )
        if existing is not None and existing.status == "verified":
            raise JarvisError("exists", "This recipient is already linked.")
        code = secrets.token_hex(8)
        recipient = existing or TelegramRecipient(user_id=user_id, label=label)
        recipient.status = "pending"
        recipient.chat_id = None
        recipient.link_code_sha256 = _hash_code(code)
        recipient.link_expires_at = utcnow() + LINK_CODE_TTL
        self.session.add(recipient)
        await self.session.flush()
        try:
            username = await telegram.bot_username()
        except TelegramError as exc:
            raise JarvisError("telegram_unavailable", exc.message, 502) from exc
        return recipient, code, f"https://t.me/{username}?start={code}"

    async def verify_recipient(
        self, user_id: uuid.UUID, recipient_id: uuid.UUID, code: str
    ) -> TelegramRecipient:
        recipient = await self.session.scalar(
            select(TelegramRecipient).where(
                TelegramRecipient.id == recipient_id, TelegramRecipient.user_id == user_id
            )
        )
        if recipient is None:
            raise JarvisError("not_found", "Recipient not found.", 404)
        if recipient.status != "pending" or recipient.link_code_sha256 != _hash_code(code):
            raise JarvisError("wrong_code", "This link code does not belong to the recipient.", 422)
        if recipient.link_expires_at is None or recipient.link_expires_at < utcnow():
            raise JarvisError("code_expired", "The link expired; create a new one.")
        try:
            start = await self._telegram().find_start(code)
        except TelegramError as exc:
            raise JarvisError("telegram_unavailable", exc.message, 502) from exc
        if start is None:
            raise JarvisError(
                "not_started",
                "Telegram has no /start message with this code yet. Ask the person to open "
                "the link and press Start, then try again.",
            )
        recipient.status, recipient.chat_id = "verified", start.chat_id
        recipient.telegram_name, recipient.verified_at = start.name, utcnow()
        recipient.link_code_sha256 = recipient.link_expires_at = None
        self._audit(user_id, "jarvis.recipient.verified", recipient.id, {"label": recipient.label})
        return recipient

    async def recipients(self, user_id: uuid.UUID) -> list[TelegramRecipient]:
        return list(
            (
                await self.session.scalars(
                    select(TelegramRecipient)
                    .where(TelegramRecipient.user_id == user_id)
                    .order_by(TelegramRecipient.label)
                )
            ).all()
        )

    def _telegram(self) -> TelegramClient:
        if self.workers.telegram is not None:
            return self.workers.telegram
        token = self.services.settings.telegram_bot_token
        if token is None or not token.get_secret_value():
            raise JarvisError(
                "telegram_not_configured",
                "Telegram is not configured on this EZO server (EZO_TELEGRAM_BOT_TOKEN).",
                503,
            )
        return TelegramClient(token.get_secret_value())

    # ------------------------------------------------------------------ tasks

    async def create_task(
        self,
        user_id: uuid.UUID,
        *,
        text: str,
        idempotency_key: str,
        device_id: uuid.UUID | None = None,
        language: str = "uz",
    ) -> JarvisTask:
        existing = await self.session.scalar(
            select(JarvisTask).where(
                JarvisTask.user_id == user_id, JarvisTask.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing
        try:
            plan = plan_document_workflow(text)
        except PlanError as exc:
            raise JarvisError(exc.code, exc.message, 422) from exc
        open_tasks = await self.session.scalar(
            select(func.count())
            .select_from(JarvisTask)
            .where(
                JarvisTask.user_id == user_id,
                JarvisTask.state.in_(("queued", "awaiting_authorization", "running")),
            )
        )
        if (open_tasks or 0) >= MAX_OPEN_TASKS:
            raise JarvisError("too_many_tasks", "Finish or cancel open tasks first.", 429)
        device = await self._choose_device(user_id, device_id)
        recipient = await self._resolve_recipient(user_id, plan)
        task = JarvisTask(
            user_id=user_id,
            device_id=device.id,
            idempotency_key=idempotency_key,
            kind="document_workflow",
            request_text=text[:2000],
            language=language,
            state="queued",
            plan={**plan.to_dict(), "recipient_id": str(recipient.id) if recipient else None},
        )
        self.session.add(task)
        await self.session.flush()
        for position, (action, params) in enumerate(self._steps(plan, recipient), start=1):
            self.session.add(
                JarvisTaskStep(task_id=task.id, position=position, action=action, params=params)
            )
        await self.session.flush()
        self._audit(user_id, "jarvis.task.created", task.id, {"plan": task.plan})
        return task

    async def _choose_device(self, user_id: uuid.UUID, device_id: uuid.UUID | None) -> JarvisDevice:
        query = select(JarvisDevice).where(
            JarvisDevice.user_id == user_id,
            JarvisDevice.status == "paired",
            JarvisDevice.capabilities.is_not(None),
        )
        if device_id is not None:
            query = query.where(JarvisDevice.id == device_id)
        devices = [
            d
            for d in (await self.session.scalars(query)).all()
            if "files.latest_documents" in (d.capabilities or [])
        ]
        if not devices:
            raise JarvisError(
                "no_paired_device",
                "No paired EZO desktop companion can read the Downloads folder. Pair one first.",
                422,
            )
        if len(devices) > 1:
            raise JarvisError(
                "device_ambiguous", "Several paired devices; choose which computer to use.", 422
            )
        return devices[0]

    async def _resolve_recipient(
        self, user_id: uuid.UUID, plan: DocumentWorkflowPlan
    ) -> TelegramRecipient | None:
        if plan.recipient is None:
            return None
        wanted = plan.recipient.lower()
        candidates = [
            r
            for r in await self.recipients(user_id)
            if r.status == "verified"
            and (r.label.lower() == wanted or wanted.startswith(r.label.lower()))
        ]
        if not candidates:
            raise JarvisError(
                "recipient_not_linked",
                f"“{plan.recipient}” is not a linked Telegram recipient. Link them first "
                "(they must press Start in EZO's bot).",
                422,
            )
        if len(candidates) > 1:
            raise JarvisError("recipient_ambiguous", "Several recipients match; be specific.", 422)
        return candidates[0]

    @staticmethod
    def _steps(
        plan: DocumentWorkflowPlan, recipient: TelegramRecipient | None
    ) -> list[tuple[str, dict[str, Any]]]:
        steps: list[tuple[str, dict[str, Any]]] = [
            (
                "files.latest_documents",
                {"root": plan.root, "count": 2 if plan.compare_previous else 1},
            )
        ]
        if plan.percentages:
            steps += [("document.extract", {}), ("compute.percentages", {})]
        if plan.convert_pdf:
            steps.append(("document.convert_pdf", {}))
        if plan.percentages:
            steps.append(("document.report_pdf", {}))
        if recipient is not None:
            steps.append(("telegram.send", {"recipient_id": str(recipient.id)}))
        return steps

    async def task(
        self, user_id: uuid.UUID, task_id: uuid.UUID, *, lock: bool = False
    ) -> JarvisTask:
        query = select(JarvisTask).where(JarvisTask.id == task_id, JarvisTask.user_id == user_id)
        task = await self.session.scalar(query.with_for_update() if lock else query)
        if task is None:
            raise JarvisError("not_found", "Task not found.", 404)
        return task

    async def steps(self, task_id: uuid.UUID) -> list[JarvisTaskStep]:
        return list(
            (
                await self.session.scalars(
                    select(JarvisTaskStep)
                    .where(JarvisTaskStep.task_id == task_id)
                    .order_by(JarvisTaskStep.position)
                )
            ).all()
        )

    async def tasks(self, user_id: uuid.UUID, limit: int = 30) -> list[JarvisTask]:
        return list(
            (
                await self.session.scalars(
                    select(JarvisTask)
                    .where(JarvisTask.user_id == user_id)
                    .order_by(JarvisTask.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def cancel(self, user_id: uuid.UUID, task_id: uuid.UUID) -> JarvisTask:
        task = await self.task(user_id, task_id, lock=True)
        if task.state in ("completed", "failed", "cancelled"):
            raise JarvisError("finished", "The task has already finished.")
        task.state, task.finished_at = "cancelled", utcnow()
        for step in await self.steps(task.id):
            if step.state in ("pending", "awaiting_authorization", "awaiting_device"):
                step.state, step.finished_at = "cancelled", utcnow()
        task.report = await self._report(task)
        self._audit(user_id, "jarvis.task.cancelled", task.id, {})
        return task

    async def retry(self, user_id: uuid.UUID, task_id: uuid.UUID) -> JarvisTask:
        task = await self.task(user_id, task_id, lock=True)
        if task.state != "failed":
            raise JarvisError("not_failed", "Only failed tasks can be retried.")
        failed = next((s for s in await self.steps(task.id) if s.state == "failed"), None)
        if failed is None or failed.action not in RETRY_SAFE_ACTIONS:
            raise JarvisError(
                "retry_unsafe",
                "This step may already have had an external effect (e.g. a Telegram message); "
                "check before creating a new task.",
            )
        failed.state, failed.error_code, failed.error_message = "pending", None, None
        failed.device_request_id = failed.device_request_expires_at = None
        task.state, task.error_code, task.finished_at = "queued", None, None
        self._audit(user_id, "jarvis.task.retried", task.id, {"step": failed.action})
        return task

    # ------------------------------------------------------------------ approval

    async def decide(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        step_id: uuid.UUID,
        *,
        scope_sha256: str,
        approve: bool,
    ) -> JarvisTask:
        task = await self.task(user_id, task_id, lock=True)
        step = next((s for s in await self.steps(task.id) if s.id == step_id), None)
        if step is None or step.state != "awaiting_authorization":
            raise JarvisError("not_awaiting", "This step is not waiting for your decision.")
        if step.scope_sha256 != scope_sha256:
            # The UI must echo exactly what it showed; a changed file or recipient differs.
            raise JarvisError("scope_changed", "The action changed; review it again.", 409)
        self.session.add(
            JarvisAuthorization(
                user_id=user_id,
                task_id=task.id,
                step_id=step.id,
                action=step.action,
                scope_sha256=scope_sha256,
                decision="approved" if approve else "rejected",
                decided_at=utcnow(),
            )
        )
        if approve:
            step.state = "pending"
            task.state = "queued"
        else:
            await self._fail(step, "rejected_by_owner", "You declined this action.")
        await self.session.flush()
        self._audit(
            user_id,
            "jarvis.step.approved" if approve else "jarvis.step.rejected",
            step.id,
            {"action": step.action, "scope_sha256": scope_sha256},
        )
        return task

    # ------------------------------------------------------------------ device work

    async def device_work(self, user_id: uuid.UUID, device_id: uuid.UUID) -> list[DeviceWork]:
        device = await self._device(user_id, device_id)
        if device.status != "paired":
            raise JarvisError("not_paired", "This device is not paired.", 403)
        device.last_seen_at = utcnow()
        rows = (
            await self.session.execute(
                select(JarvisTaskStep, JarvisTask)
                .join(JarvisTask, JarvisTask.id == JarvisTaskStep.task_id)
                .where(
                    JarvisTask.device_id == device.id,
                    JarvisTask.state == "running",
                    JarvisTaskStep.state == "awaiting_device",
                )
            )
        ).all()
        work = []
        for step, task in rows:
            if step.device_request_expires_at is None or step.device_request_id is None:
                continue
            if step.device_request_expires_at < utcnow():
                continue
            work.append(
                DeviceWork(
                    request_id=step.device_request_id,
                    task_id=task.id,
                    device_id=device.id,
                    action="files.latest_documents",
                    root="downloads",
                    count=int(step.params.get("count", 1)),
                    extensions=list(DEVICE_EXTENSIONS),
                    expires_at=int(step.device_request_expires_at.timestamp()),
                )
            )
        return work

    async def submit_device_result(
        self, user_id: uuid.UUID, device_id: uuid.UUID, result: SignedDeviceResult
    ) -> JarvisTask:
        device = await self._device(user_id, device_id)
        if device.status != "paired":
            raise JarvisError("not_paired", "This device is not paired.", 403)
        try:
            verify_result(result, device.public_key)
        except ValueError as exc:
            raise JarvisError("invalid_signature", "The device signature is invalid.", 422) from exc
        payload = result.payload
        if payload.device_id != device.id:
            raise JarvisError("wrong_device", "The result names another device.", 422)
        task = await self.task(user_id, payload.task_id, lock=True)
        step = next(
            (
                s
                for s in await self.steps(task.id)
                if s.state == "awaiting_device" and s.device_request_id == payload.request_id
            ),
            None,
        )
        if step is None or task.device_id != device.id or task.state != "running":
            raise JarvisError("no_pending_work", "No matching work is waiting for this result.")
        if step.device_request_expires_at is None or step.device_request_expires_at < utcnow():
            await self._fail(step, "device_timeout", "The device answered too late.")
            return task
        if payload.outcome != "completed":
            await self._fail(
                step, "device_" + payload.outcome, payload.reason or "The device refused."
            )
            return task
        if payload.latest_ambiguous:
            await self._fail(
                step,
                "latest_ambiguous",
                "Two files have the same newest time; open the one you mean and retry.",
            )
            return task
        wanted = int(step.params.get("count", 1))
        if len(payload.files) != wanted:
            await self._fail(
                step, "not_enough_files", f"Expected {wanted} supported files in Downloads."
            )
            return task
        files: list[dict[str, Any]] = []
        for item in payload.files:  # newest first, as the device reports
            key = f"jarvis/{task.id}/{item.sha256}"
            await self.services.storage.put(key, item.content())
            files.append(
                {
                    "name": item.name,
                    "extension": item.extension,
                    "size_bytes": item.size_bytes,
                    "modified_ms": item.modified_ms,
                    "sha256": item.sha256,
                    "storage_key": key,
                }
            )
        if wanted == 2 and files[0]["modified_ms"] < files[1]["modified_ms"]:
            files.reverse()
        step.output = {"files": files}
        step.receipt = {
            "device_id": str(device.id),
            "request_id": str(payload.request_id),
            "signature_verified": True,
        }
        step.state, step.finished_at = "completed", utcnow()
        task.state = "queued"
        self._audit(user_id, "jarvis.device.result", step.id, {"files": len(files)})
        return task

    # ------------------------------------------------------------------ execution

    async def advance(self, task: JarvisTask) -> JarvisTask:
        """Run the steps this process can run, stopping at a device, approval or worker."""
        for _ in range(16):
            if task.state in ("completed", "failed", "cancelled"):
                return task
            steps = await self.steps(task.id)
            step = next((s for s in steps if s.state != "completed"), None)
            if step is None:
                task.state, task.finished_at = "completed", utcnow()
                task.report = await self._report(task)
                self._audit(task.user_id, "jarvis.task.completed", task.id, {})
                return task
            if step.state in ("failed", "cancelled"):
                return await self._finish_failed(task, step)
            if step.state == "awaiting_authorization":
                task.state = "awaiting_authorization"
                return task
            if step.state == "awaiting_device":
                if step.device_request_expires_at and step.device_request_expires_at < utcnow():
                    await self._fail(step, "device_timeout", "The device did not answer in time.")
                    continue
                task.state = "running"
                return task
            if step.state == "running":
                return task  # another process holds it
            if not await self._claim(step):
                return task
            task.state = "running"
            outcome = await self._run(task, step, steps)
            await self.session.flush()
            if outcome == "wait":
                return task
        return task

    async def _claim(self, step: JarvisTaskStep) -> bool:
        claimed = await self.session.execute(
            update(JarvisTaskStep)
            .where(JarvisTaskStep.id == step.id, JarvisTaskStep.state == "pending")
            .values(state="running", started_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            return False
        await self.session.refresh(step)
        return True

    def _release(self, step: JarvisTaskStep) -> str:
        step.state, step.started_at = "pending", None
        return "wait"

    async def _run(
        self, task: JarvisTask, step: JarvisTaskStep, steps: list[JarvisTaskStep]
    ) -> str:
        outputs = {s.action: s.output for s in steps if s.state == "completed"}
        files: list[dict[str, Any]] = outputs.get("files.latest_documents", {}).get("files", [])
        try:
            if step.action == "files.latest_documents":
                step.device_request_id = uuid.uuid4()
                step.device_request_expires_at = utcnow() + DEVICE_WORK_TTL
                step.state = "awaiting_device"
                return "wait"
            if step.action == "document.extract":
                texts = []
                for item in files:
                    text = await self._extract(item)
                    if text is None:
                        return self._release(step)  # waits for the isolated worker
                    texts.append(text)
                step.output = {"texts": [t[:200_000] for t in texts]}
            elif step.action == "compute.percentages":
                texts = outputs["document.extract"]["texts"]
                comparison = percentages.compare(texts[1], texts[0])
                if not comparison.rows:
                    raise JarvisError(
                        "no_percentages", "No labelled percentages were found in the previous file."
                    )
                step.output = {
                    "markdown": percentages.report_markdown(
                        comparison, files[1]["name"], files[0]["name"]
                    ),
                    "matched": comparison.matched,
                    "rows": len(comparison.rows),
                }
            elif step.action == "document.convert_pdf":
                pdf = await self._convert(files[0])
                if pdf is None:
                    return self._release(step)
                step.output = await self._store_pdf(task, pdf, files[0]["name"], "converted")
            elif step.action == "document.report_pdf":
                pdf = await self._report_pdf(
                    outputs["compute.percentages"]["markdown"], files[0]["name"]
                )
                step.output = await self._store_pdf(task, pdf, files[0]["name"], "foizlar")
            elif step.action == "telegram.send":
                return await self._send(task, step, steps)
            else:  # pragma: no cover - the step list is built from a fixed registry
                raise JarvisError("unknown_action", step.action)
        except JarvisError as exc:
            await self._fail(step, exc.code, exc.message)
            return "continue"
        step.state, step.finished_at = "completed", utcnow()
        return "continue"

    async def _extract(self, item: dict[str, Any]) -> str | None:
        data: bytes = await self.services.storage.get(item["storage_key"])
        if item["extension"] in TEXT_FORMATS:
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise JarvisError("not_utf8", f"{item['name']} is not UTF-8 text.") from exc
        if self.workers.extractor is None:
            return None  # never parsed in the API process
        try:
            text: str = await self.workers.extractor(data, item["extension"])
            return text
        except Exception as exc:
            raise JarvisError("extract_failed", f"{item['name']} could not be read.") from exc

    async def _convert(self, item: dict[str, Any]) -> bytes | None:
        data: bytes = await self.services.storage.get(item["storage_key"])
        if item["extension"] == "pdf":
            if not data.startswith(b"%PDF-"):
                raise JarvisError("not_pdf", f"{item['name']} is not a PDF.")
            return data
        if item["extension"] in TEXT_FORMATS:
            from ezo_api.tools.document_tools import render_document

            text = data.decode("utf-8", errors="replace")
            files = render_document("```\n" + text[:200_000] + "\n```", item["name"], "pdf", None)
            pdf: bytes = files["pdf"]
            return pdf
        if self.workers.converter is None:
            return None
        try:
            converted: bytes = await self.workers.converter(data, item["extension"])
            return converted
        except Exception as exc:
            raise JarvisError("convert_failed", f"{item['name']} could not be converted.") from exc

    async def _report_pdf(self, markdown: str, name: str) -> bytes:
        from ezo_api.tools.document_tools import render_document

        files = render_document(markdown, f"Foiz ko'rsatkichlari — {name}", "pdf", None)
        return files["pdf"]

    async def _store_pdf(
        self, task: JarvisTask, pdf: bytes, source: str, suffix: str
    ) -> dict[str, Any]:
        stem = source.rsplit(".", 1)[0][:80] or "hujjat"
        created = await self.services.artifacts.create(
            self.session,
            task.user_id,
            title=f"{stem} ({suffix})",
            artifact_type="document",
            filename=f"{stem}-{suffix}.pdf",
            data=pdf,
            created_by_agent="jarvis",
            generation_metadata={"task_id": str(task.id), "source": source},
        )
        return {
            "artifact_id": str(created.artifact.id),
            "filename": f"{stem}-{suffix}.pdf",
            "sha256": hashlib.sha256(pdf).hexdigest(),
            "size_bytes": len(pdf),
        }

    async def _documents(self, steps: list[JarvisTaskStep]) -> list[dict[str, Any]]:
        return [
            s.output
            for s in steps
            if s.action in ("document.convert_pdf", "document.report_pdf")
            and s.state == "completed"
        ]

    async def _send(
        self, task: JarvisTask, step: JarvisTaskStep, steps: list[JarvisTaskStep]
    ) -> str:
        recipient = await self.session.get(
            TelegramRecipient, uuid.UUID(step.params["recipient_id"])
        )
        if recipient is None or recipient.user_id != task.user_id or recipient.status != "verified":
            raise JarvisError("recipient_not_linked", "The recipient is no longer linked.")
        documents = await self._documents(steps)
        if not documents:
            raise JarvisError("nothing_to_send", "No document was produced to send.")
        scope = _sha(
            {
                "action": "telegram.send",
                "chat_id": recipient.chat_id,
                "documents": sorted(d["sha256"] for d in documents),
            }
        )
        approval = await self.session.scalar(
            select(JarvisAuthorization).where(JarvisAuthorization.step_id == step.id)
        )
        if approval is None or approval.decision != "approved" or approval.scope_sha256 != scope:
            step.scope_sha256 = scope
            step.output = {
                "recipient": recipient.label,
                "telegram_name": recipient.telegram_name,
                "documents": [
                    {"filename": d["filename"], "sha256": d["sha256"]} for d in documents
                ],
            }
            step.state, step.started_at = "awaiting_authorization", None
            task.state = "awaiting_authorization"
            return "wait"
        if approval.used_at is not None:
            raise JarvisError("approval_used", "This approval was already used.")
        approval.used_at = utcnow()
        await self.session.flush()
        receipts = []
        try:
            telegram = self._telegram()
            for document in documents:
                artifact_bytes = await self._artifact_bytes(task, document["artifact_id"])
                receipt = await telegram.send_document(
                    recipient.chat_id or "",
                    artifact_bytes,
                    document["filename"],
                    caption="EZO",
                )
                receipts.append(receipt.to_dict())
        except TelegramError as exc:
            step.receipt = {"delivered": receipts}
            code = "delivery_unknown" if exc.outcome_unknown else "delivery_failed"
            raise JarvisError(code, exc.message) from exc
        step.receipt = {"delivered": receipts}
        step.state, step.finished_at = "completed", utcnow()
        return "continue"

    async def _artifact_bytes(self, task: JarvisTask, artifact_id: str) -> bytes:
        from ezo_api.db.models import Artifact

        artifact = await self.session.get(Artifact, uuid.UUID(artifact_id))
        if artifact is None or artifact.user_id != task.user_id:
            raise JarvisError("artifact_missing", "The produced file no longer exists.")
        version = await self.services.artifacts.current_version(self.session, artifact)
        if version is None:
            raise JarvisError("artifact_missing", "The produced file has no content.")
        return bytes(await self.services.artifacts.read(version))

    async def _fail(self, step: JarvisTaskStep, code: str, message: str) -> None:
        step.state, step.finished_at = "failed", utcnow()
        step.error_code, step.error_message = code[:40], message[:300]

    async def _finish_failed(self, task: JarvisTask, step: JarvisTaskStep) -> JarvisTask:
        if step.state == "cancelled":
            task.state = "cancelled"
        else:
            task.state, task.error_code = "failed", step.error_code
        task.finished_at = utcnow()
        task.report = await self._report(task)
        self._audit(task.user_id, f"jarvis.task.{task.state}", task.id, {"step": step.action})
        return task

    async def _report(self, task: JarvisTask) -> str:
        """Truthful Uzbek summary built only from recorded step outcomes."""
        lines: list[str] = []
        labels = {
            "files.latest_documents": "Downloads fayllari",
            "document.extract": "Matnni o'qish",
            "compute.percentages": "Foizlarni hisoblash",
            "document.convert_pdf": "PDF'ga aylantirish",
            "document.report_pdf": "Foizlar hisoboti (PDF)",
            "telegram.send": "Telegram orqali yuborish",
        }
        for step in await self.steps(task.id):
            name = labels.get(step.action, step.action)
            if step.state == "completed":
                detail = ""
                if step.action == "files.latest_documents":
                    detail = ": " + ", ".join(f["name"] for f in step.output.get("files", []))
                elif step.action == "telegram.send":
                    ids = [str(r["message_id"]) for r in step.receipt.get("delivered", [])]
                    detail = f" — Telegram xabar ID: {', '.join(ids)}"
                lines.append(f"✅ {name}{detail}")
            elif step.state == "failed":
                lines.append(f"❌ {name}: {step.error_message}")
            elif step.state == "cancelled":
                lines.append(f"⏹ {name}: bekor qilindi")
            else:
                lines.append(f"… {name}: bajarilmadi")
        head = {
            "completed": "Vazifa bajarildi.",
            "failed": "Vazifa to'xtadi.",
            "cancelled": "Vazifa bekor qilindi.",
        }.get(task.state, "Vazifa davom etmoqda.")
        return head + "\n" + "\n".join(lines)
