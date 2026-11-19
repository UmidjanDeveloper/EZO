"""Computer actions through JARVIS: nothing reaches the computer before the owner approves
that exact action, and only a result signed by the paired key completes it."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from ezo_api.jarvis.device_protocol import RESULT_DOMAIN, DeviceResultPayload, canonical
from tests.integration.test_jarvis_tasks import Device as FilesOnlyDevice
from tests.integration.test_jarvis_tasks import pair, start


class Device(FilesOnlyDevice):
    """A computer whose EZO app declares the computer actions."""

    def pairing_body(self, name: str = "Owner PC") -> dict[str, Any]:
        body = super().pairing_body(name)
        body["capabilities"] = [
            "files.latest_documents", "pc.open_app", "pc.list_folder", "pc.open_file",
            "pc.open_url",
        ]  # fmt: skip
        return body


def signed(device: Device, work: dict[str, Any], **fields: Any) -> dict[str, Any]:
    payload = DeviceResultPayload(
        request_id=work["request_id"], task_id=work["task_id"], device_id=work["device_id"],
        action=work["action"], outcome=fields.pop("outcome", "completed"), **fields,
    )  # fmt: skip
    return {
        "payload": payload.model_dump(mode="json"),
        "signature": device.key.sign(RESULT_DOMAIN + canonical(payload)).hex(),
    }


async def decide(
    client: AsyncClient, task: dict[str, Any], approve: bool, scope: str | None = None
):
    [step] = task["steps"]
    return await client.post(
        f"/api/jarvis/tasks/{task['id']}/steps/{step['id']}/decision",
        json={"scope_sha256": scope or step["scope_sha256"], "approve": approve},
    )


async def work_of(client: AsyncClient, device: Device) -> list[dict[str, Any]]:
    return (await client.get(f"/api/jarvis/devices/{device.id}/work")).json()  # type: ignore[no-any-return]


async def test_open_app_waits_for_approval_then_runs_on_the_device(client: AsyncClient) -> None:
    device = Device()
    await pair(client, device)
    task = await start(client, "Kompyuterda kalkulyatorni och")
    assert task["kind"] == "pc_action" and task["state"] == "awaiting_authorization"
    [step] = task["steps"]
    assert step["action"] == "pc.open_app" and step["state"] == "awaiting_authorization"
    assert step["output"]["pc"]["description"] == "«Kalkulyator» dasturini ochish"
    assert await work_of(client, device) == []  # nothing reaches the computer yet

    assert (await decide(client, task, True, scope="0" * 64)).status_code == 409
    approved = await decide(client, task, True)
    assert approved.status_code == 200, approved.text
    [work] = await work_of(client, device)
    assert (work["action"], work["target"], work["root"]) == (
        "pc.open_app",
        "calculator",
        "downloads",
    )

    done = await client.post(f"/api/jarvis/devices/{device.id}/results", json=signed(device, work))
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "completed"
    assert "«Kalkulyator» dasturini ochish" in done.json()["report"]
    assert await work_of(client, device) == []


async def test_folder_listing_returns_names_only(client: AsyncClient) -> None:
    device = Device()
    await pair(client, device)
    task = await start(client, "Yuklamalar papkasida nima bor?")
    await decide(client, task, True)
    [work] = await work_of(client, device)
    entries = [
        {"name": "hisobot.docx", "is_dir": False, "size_bytes": 1200, "modified_ms": 5},
        {"name": "Rasmlar", "is_dir": True, "size_bytes": 0, "modified_ms": 6},
    ]
    done = await client.post(
        f"/api/jarvis/devices/{device.id}/results", json=signed(device, work, entries=entries)
    )
    assert done.json()["state"] == "completed"
    assert "2 ta: hisobot.docx, Rasmlar/" in done.json()["report"]


async def test_declined_or_mismatched_results_do_nothing(client: AsyncClient) -> None:
    device = Device()
    await pair(client, device)
    declined = await start(client, "kompyuterda notepadni och")
    response = await decide(client, declined, False)
    assert response.json()["state"] == "failed" and await work_of(client, device) == []

    task = await start(client, "https://lex.uz saytini och")
    await decide(client, task, True)
    [work] = await work_of(client, device)
    assert work["target"] == "https://lex.uz"
    other = dict(work, action="pc.open_app")
    wrong = await client.post(
        f"/api/jarvis/devices/{device.id}/results", json=signed(device, other)
    )
    assert wrong.status_code == 422  # a result for another action is refused
    forged = signed(Device(), work)
    bad = await client.post(f"/api/jarvis/devices/{device.id}/results", json=forged)
    assert bad.status_code == 422  # not signed by the paired key
    refused = await client.post(
        f"/api/jarvis/devices/{device.id}/results",
        json=signed(device, work, outcome="refused", reason="PC control is off on this computer."),
    )
    assert refused.json()["state"] == "failed"
    assert "PC control is off" in refused.json()["report"]


async def test_dangerous_files_are_not_computer_actions(client: AsyncClient) -> None:
    device = Device()
    await pair(client, device)
    response = await client.post(
        "/api/jarvis/tasks",
        json={"text": "kompyuterda virus.exe ni och", "idempotency_key": "dangerous-file-1"},
    )
    assert response.status_code == 422  # not a pc action, and not a document workflow either


async def test_an_older_computer_app_gets_no_computer_actions(client: AsyncClient) -> None:
    device = FilesOnlyDevice()
    await pair(client, device)
    response = await client.post(
        "/api/jarvis/tasks",
        json={"text": "kalkulyatorni och", "idempotency_key": "old-computer-app-1"},
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "device_cannot"


async def test_chat_creates_the_task_and_waits_for_approval(
    client: AsyncClient, fake_anthropic
) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import stream_chat

    device = Device()
    await pair(client, device)
    fake_anthropic.reply = "Tasdiqlashingizni kutyapman."
    events = await stream_chat(client, message="Kalkulyatorni och")
    assert events[0][1]["agent"] == "computer"
    assert "WAITING for the owner's approval" in (fake_anthropic.requests[-1].system or "")
    [task] = (await client.get("/api/jarvis/tasks")).json()
    assert task["kind"] == "pc_action" and task["state"] == "awaiting_authorization"
    assert await work_of(client, device) == []


async def test_chat_without_a_paired_computer_explains_pairing(
    client: AsyncClient, fake_anthropic
) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import stream_chat

    fake_anthropic.reply = "Avval kompyuterni ulang."
    events = await stream_chat(client, message="Kalkulyatorni och")
    assert events[0][1]["agent"] == "computer"
    assert "Bu kompyuterni ulash" in (fake_anthropic.requests[-1].system or "")
