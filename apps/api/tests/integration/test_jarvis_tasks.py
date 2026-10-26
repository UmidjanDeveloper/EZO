"""JARVIS governed task engine end to end over the real API and database.

Real: HTTP routes, durable tables, Ed25519 device keys and signatures, approval
hash binding, artifacts (real PDFs). Test doubles: the Telegram HTTP endpoint
(httpx MockTransport, same wire format) and, for Office files, the isolated worker.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
import time
import uuid
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from httpx import AsyncClient
from pypdf import PdfReader

from ezo_api.jarvis import service as jarvis_service
from ezo_api.jarvis.device_protocol import (
    RESULT_DOMAIN,
    DeviceResultPayload,
    canonical,
    pairing_message,
)
from ezo_api.jarvis.telegram import TelegramClient

REFERENCE = (
    "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini "
    "undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor."
)
PREVIOUS = b"Sentyabr\nIshsizlik darajasi: 12,5%\nInflyatsiya: 9.8%\n"
CURRENT = b"Oktyabr\nIshsizlik darajasi: 11%\nInflyatsiya: 10.1%\n"


class FakeTelegram:
    """Speaks the Bot API wire format; records what EZO sent."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.fail_send: httpx.Response | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "ezo_test_bot"}})
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        if method == "sendDocument":
            if self.fail_send is not None:
                return self.fail_send
            body = request.content
            self.sent.append({"size": len(body), "pdf": b"%PDF-" in body})
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 100 + len(self.sent),
                        "date": int(time.time()),
                        "chat": {"id": 555001, "type": "private"},
                        "document": {"file_name": "x.pdf"},
                    },
                },
            )
        return httpx.Response(404, json={"ok": False, "description": "not found"})


@pytest.fixture
def telegram(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    fake = FakeTelegram()
    client = TelegramClient("42:test-token", transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(jarvis_service.JarvisService, "_telegram", lambda self: client)
    return fake


class Device:
    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.id = ""

    def pairing_body(self, name: str = "Owner PC") -> dict[str, Any]:
        nonce = secrets.token_hex(16)
        signature = self.key.sign(pairing_message(name, "windows", nonce)).hex()
        return {
            "name": name,
            "platform": "windows",
            "public_key": self.public,
            "nonce": nonce,
            "signature": signature,
            "capabilities": ["files.latest_documents"],
        }

    def result(self, work: dict[str, Any], files: list[tuple[str, bytes, int]], **extra: Any):
        payload = DeviceResultPayload(
            request_id=work["request_id"],
            task_id=work["task_id"],
            device_id=work["device_id"],
            action="files.latest_documents",
            outcome=extra.pop("outcome", "completed"),
            files=[
                {
                    "name": name,
                    "extension": name.rsplit(".", 1)[-1],
                    "size_bytes": len(data),
                    "modified_ms": modified,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "content_base64": base64.b64encode(data).decode(),
                }
                for name, data, modified in files
            ],
            **extra,
        )
        signature = self.key.sign(RESULT_DOMAIN + canonical(payload)).hex()
        return {"payload": payload.model_dump(mode="json"), "signature": signature}


async def pair(client: AsyncClient, device: Device) -> str:
    requested = await client.post("/api/jarvis/devices/pairing", json=device.pairing_body())
    assert requested.status_code == 201, requested.text
    body = requested.json()
    assert body["device"]["status"] == "pending"
    wrong = "000000" if body["code"] != "000000" else "111111"
    assert (
        await client.post(
            f"/api/jarvis/devices/{body['device']['id']}/confirm", json={"code": wrong}
        )
    ).status_code == 422
    confirmed = await client.post(
        f"/api/jarvis/devices/{body['device']['id']}/confirm", json={"code": body["code"]}
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "paired"
    device.id = body["device"]["id"]
    return device.id


async def link_recipient(
    client: AsyncClient, telegram: FakeTelegram, label: str = "Baxtiyor"
) -> str:
    created = await client.post("/api/jarvis/telegram/recipients", json={"label": label})
    assert created.status_code == 201, created.text
    code = created.json()["code"]
    assert created.json()["link"] == f"https://t.me/ezo_test_bot?start={code}"
    recipient_id = created.json()["recipient"]["id"]
    not_yet = await client.post(
        f"/api/jarvis/telegram/recipients/{recipient_id}/verify", json={"code": code}
    )
    assert not_yet.status_code == 409 and not_yet.json()["error"]["code"] == "not_started"
    telegram.updates.append(
        {
            "message": {
                "text": f"/start {code}",
                "chat": {"id": 555001, "type": "private"},
                "from": {"first_name": label},
            }
        }
    )
    verified = await client.post(
        f"/api/jarvis/telegram/recipients/{recipient_id}/verify", json={"code": code}
    )
    assert verified.status_code == 200 and verified.json()["status"] == "verified"
    return recipient_id


async def start(client: AsyncClient, text: str = REFERENCE, key: str | None = None) -> dict:
    response = await client.post(
        "/api/jarvis/tasks", json={"text": text, "idempotency_key": key or uuid.uuid4().hex}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def deliver_files(
    client: AsyncClient, device: Device, files: list[tuple[str, bytes, int]], **extra: Any
) -> dict:
    work = (await client.get(f"/api/jarvis/devices/{device.id}/work")).json()
    assert len(work) == 1 and work[0]["root"] == "downloads"
    response = await client.post(
        f"/api/jarvis/devices/{device.id}/results", json=device.result(work[0], files, **extra)
    )
    assert response.status_code == 200, response.text
    return response.json()


def step(task: dict, action: str) -> dict:
    return next(s for s in task["steps"] if s["action"] == action)


async def test_reference_scenario_with_approval_and_real_receipts(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    device = Device()
    await pair(client, device)
    await link_recipient(client, telegram)
    task = await start(client)
    assert task["state"] == "running"
    assert [s["action"] for s in task["steps"]] == [
        "files.latest_documents",
        "document.extract",
        "compute.percentages",
        "document.convert_pdf",
        "document.report_pdf",
        "telegram.send",
    ]
    assert step(task, "files.latest_documents")["state"] == "awaiting_device"

    task = await deliver_files(
        client, device, [("oktyabr.txt", CURRENT, 2_000), ("sentyabr.txt", PREVIOUS, 1_000)]
    )
    assert task["state"] == "awaiting_authorization"
    send = step(task, "telegram.send")
    assert send["state"] == "awaiting_authorization" and telegram.sent == []
    assert send["output"]["recipient"] == "Baxtiyor"
    assert len(send["output"]["documents"]) == 2

    # The approval must echo exactly what was shown.
    stale = await client.post(
        f"/api/jarvis/tasks/{task['id']}/steps/{send['id']}/decision",
        json={"scope_sha256": "0" * 64, "approve": True},
    )
    assert stale.status_code == 409 and telegram.sent == []
    approved = await client.post(
        f"/api/jarvis/tasks/{task['id']}/steps/{send['id']}/decision",
        json={"scope_sha256": send["scope_sha256"], "approve": True},
    )
    task = approved.json()
    assert task["state"] == "completed", task
    receipts = step(task, "telegram.send")["receipt"]["delivered"]
    assert [r["message_id"] for r in receipts] == [101, 102]
    assert len(telegram.sent) == 2 and all(s["pdf"] for s in telegram.sent)
    assert "Telegram xabar ID: 101, 102" in task["report"]

    report = step(task, "document.report_pdf")["output"]
    pdf = await client.get(f"/api/artifacts/{report['artifact_id']}/versions/1/download")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "12.5" in text and "-1.5" in text and "+0.3" in text
    converted = step(task, "document.convert_pdf")["output"]
    assert converted["filename"] == "oktyabr-converted.pdf"

    # Approvals are single use: a repeated decision changes nothing.
    again = await client.post(
        f"/api/jarvis/tasks/{task['id']}/steps/{send['id']}/decision",
        json={"scope_sha256": send["scope_sha256"], "approve": True},
    )
    assert again.status_code == 409 and len(telegram.sent) == 2


async def test_rejection_and_cancellation_never_send(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    device = Device()
    await pair(client, device)
    await link_recipient(client, telegram)
    task = await start(client)
    task = await deliver_files(client, device, [("b.txt", CURRENT, 2), ("a.txt", PREVIOUS, 1)])
    send = step(task, "telegram.send")
    rejected = await client.post(
        f"/api/jarvis/tasks/{task['id']}/steps/{send['id']}/decision",
        json={"scope_sha256": send["scope_sha256"], "approve": False},
    )
    assert rejected.json()["state"] == "failed"
    assert rejected.json()["error_code"] == "rejected_by_owner"
    retry = await client.post(f"/api/jarvis/tasks/{task['id']}/retry")
    assert retry.status_code == 409 and retry.json()["error"]["code"] == "retry_unsafe"

    second = await start(client)
    cancelled = await client.post(f"/api/jarvis/tasks/{second['id']}/cancel")
    assert cancelled.json()["state"] == "cancelled"
    assert "bekor qilindi" in cancelled.json()["report"]
    assert (await client.get(f"/api/jarvis/devices/{device.id}/work")).json() == []
    assert telegram.sent == []


async def test_device_results_must_be_signed_by_the_paired_key(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    device, impostor = Device(), Device()
    await pair(client, device)
    await link_recipient(client, telegram)
    await start(client)
    work = (await client.get(f"/api/jarvis/devices/{device.id}/work")).json()[0]
    forged = impostor.result(work, [("b.txt", CURRENT, 2), ("a.txt", PREVIOUS, 1)])
    response = await client.post(f"/api/jarvis/devices/{device.id}/results", json=forged)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_signature"
    tampered = device.result(work, [("b.txt", CURRENT, 2), ("a.txt", PREVIOUS, 1)])
    tampered["payload"]["files"][0]["name"] = "evil.txt"
    response = await client.post(f"/api/jarvis/devices/{device.id}/results", json=tampered)
    assert response.status_code == 422
    # Revoking the device stops the task honestly.
    await client.delete(f"/api/jarvis/devices/{device.id}")
    tasks = (await client.get("/api/jarvis/tasks")).json()
    task = (await client.get(f"/api/jarvis/tasks/{tasks[0]['id']}")).json()
    assert task["state"] == "failed" and task["error_code"] == "device_revoked"


async def test_ambiguous_newest_file_and_delivery_failure_are_reported(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    device = Device()
    await pair(client, device)
    await link_recipient(client, telegram)
    await start(client)
    task = await deliver_files(
        client,
        device,
        [("b.txt", CURRENT, 5), ("a.txt", PREVIOUS, 5)],
        latest_ambiguous=True,
    )
    assert task["state"] == "failed" and task["error_code"] == "latest_ambiguous"
    retried = await client.post(f"/api/jarvis/tasks/{task['id']}/retry")
    assert retried.json()["state"] == "running"  # safe: re-asks the device

    task = await deliver_files(client, device, [("b.txt", CURRENT, 6), ("a.txt", PREVIOUS, 5)])
    send = step(task, "telegram.send")
    telegram.fail_send = httpx.Response(403, json={"ok": False, "description": "bot was blocked"})
    task = (
        await client.post(
            f"/api/jarvis/tasks/{task['id']}/steps/{send['id']}/decision",
            json={"scope_sha256": send["scope_sha256"], "approve": True},
        )
    ).json()
    assert task["state"] == "failed" and task["error_code"] == "delivery_failed"
    assert "bot was blocked" in step(task, "telegram.send")["error_message"]
    assert "yuborildi" not in task["report"] and "xabar ID" not in task["report"]


async def test_office_files_wait_for_the_isolated_worker(
    client: AsyncClient, app, telegram: FakeTelegram
) -> None:
    device = Device()
    await pair(client, device)
    task = await start(client, "Downloads ichidagi eng oxirgi faylni PDF'ga aylantir")
    task = await deliver_files(client, device, [("hisobot.docx", b"PK\x03\x04docx", 3)])
    convert = step(task, "document.convert_pdf")
    assert task["state"] == "running" and convert["state"] == "pending"  # never parsed here

    from ezo_api.db.models import JarvisTask
    from ezo_api.jarvis.service import JarvisService, Workers

    calls: list[str] = []

    async def converter(data: bytes, extension: str) -> bytes:
        calls.append(extension)
        return b"%PDF-1.7 converted by the isolated worker"

    async with app.state.services.db.sessionmaker() as session:
        row = await session.get(JarvisTask, uuid.UUID(task["id"]))
        await JarvisService(session, app.state.services, Workers(converter=converter)).advance(row)
        await session.commit()
    task = (await client.get(f"/api/jarvis/tasks/{task['id']}")).json()
    assert calls == ["docx"] and task["state"] == "completed"


async def test_prerequisites_are_enforced_not_assumed(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    no_device = await client.post(
        "/api/jarvis/tasks", json={"text": REFERENCE, "idempotency_key": "k-no-device"}
    )
    assert no_device.json()["error"]["code"] == "no_paired_device"
    before = (await client.get("/api/jarvis/capabilities")).json()["device_features"]
    assert before["windows_downloads"]["available"] is False
    device = Device()
    await pair(client, device)
    after = (await client.get("/api/jarvis/capabilities")).json()["device_features"]
    assert after["windows_downloads"]["available"] is True
    assert after["windows_downloads"]["execution_authorized"] is False  # still per task
    assert "configured_telegram_integration" in after["telegram_send"]["missing_prerequisites"]
    not_linked = await client.post(
        "/api/jarvis/tasks", json={"text": REFERENCE, "idempotency_key": "k-no-recipient"}
    )
    assert not_linked.json()["error"]["code"] == "recipient_not_linked"
    vague = await client.post(
        "/api/jarvis/tasks", json={"text": "Kompyuterimni tozalab ber", "idempotency_key": "k-v"}
    )
    assert vague.status_code == 422
    await link_recipient(client, telegram)
    first = await start(client, key="same-key-123")
    second = await start(client, key="same-key-123")
    assert first["id"] == second["id"]  # idempotent creation


async def test_tasks_and_devices_are_owner_scoped(
    client: AsyncClient, app, telegram: FakeTelegram
) -> None:
    from ezo_api.db.models import User

    device = Device()
    await pair(client, device)
    await link_recipient(client, telegram)
    task = await start(client)
    async with app.state.services.db.sessionmaker() as session:
        other = User(id=uuid.uuid4(), email="other@example.com", display_name="Other")
        session.add(other)
        await session.commit()
    from ezo_api.jarvis.service import JarvisError, JarvisService

    async with app.state.services.db.sessionmaker() as session:
        service = JarvisService(session, app.state.services)
        for call in (
            service.task(other.id, uuid.UUID(task["id"])),
            service.device_work(other.id, uuid.UUID(device.id)),
            service.cancel(other.id, uuid.UUID(task["id"])),
        ):
            with pytest.raises(JarvisError) as caught:
                await call
            assert caught.value.status == 404
        assert await service.tasks(other.id) == []
        assert json.dumps(await service.recipients(other.id), default=str) == "[]"
