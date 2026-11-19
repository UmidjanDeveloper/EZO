"""Skills: EZO writes code, the owner approves that exact code, a worker runs it in a box."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from ezo_api.db.models import AuditLog, Skill, SkillRun, User
from ezo_api.skills import service as skills
from ezo_api.skills.sandbox import SandboxResult, docker_args
from ezo_api.skills.worker import run_once
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

CODE = '''def run(data):
    """Monthly annuity payment."""
    amount = float(data["amount"])
    months = int(data["months"])
    rate = float(data["rate"]) / 100 / 12
    payment = amount * rate / (1 - (1 + rate) ** -months)
    return {"oylik_tolov": round(payment)}
'''


class FakeSandbox:
    """Runs the code in-process — only for tests; the real worker uses a locked container."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def run(self, code: str, data: Any) -> SandboxResult:
        self.calls.append((code, data))
        namespace: dict[str, Any] = {}
        exec(compile(code, "<skill>", "exec"), namespace)  # noqa: S102 - test double
        try:
            return SandboxResult(True, namespace["run"](data), None, 5)
        except Exception as exc:
            return SandboxResult(False, None, f"{type(exc).__name__}: {exc}", 5)


async def make_owner(app: FastAPI, client: AsyncClient) -> None:
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        assert user is not None
        user.role = "super_admin"
        await session.commit()


def test_check_code_reports_problems() -> None:
    assert skills.check_code(CODE) == {"ok": True, "problems": [], "imports": []}
    bad = skills.check_code("import os\ndef run(data):\n    return open('/etc/passwd').read()\n")
    assert not bad["ok"]
    assert any("“os”" in p for p in bad["problems"])
    assert any("“open”" in p for p in bad["problems"])
    assert "must define a top-level function run" in " ".join(
        skills.check_code("x = 1\n")["problems"]
    )
    assert not skills.check_code("def run(d):\n    return ().__class__.__bases__\n")["ok"]
    assert skills.check_code("def run(:\n")["problems"][0].startswith("Syntax error")


def test_sandbox_is_locked_down() -> None:
    args = docker_args("sha256:" + "a" * 64, "ezo-skill-x")
    joined = " ".join(args)
    for flag in (
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "--user 10001:10001",
        "--pids-limit 32",
        "--memory 256m",
        "no-new-privileges:true",
    ):
        assert flag in joined
    assert "-v" not in args and "--volume" not in args and "--privileged" not in args


async def test_draft_approve_run_flow(
    app: FastAPI, client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await make_owner(app, client)
    written = {
        "name": "Kredit kalkulyatori",
        "description": "Oylik kredit to'lovini hisoblaydi.",
        "input_hint": '{"amount": summa, "months": oy, "rate": yillik foiz}',
        "code": CODE,
    }
    fake_anthropic.replies = [json.dumps(written), "Qoralama tayyor."]
    events = await stream_chat(client, message="O'zingga kredit kalkulyatori vositasini qo'sh")
    assert events[0][1]["agent"] == "skill"
    system = fake_anthropic.requests[-1].system or ""
    assert "skill DRAFT «Kredit kalkulyatori»" in system and "checks passed" in system

    listing = (await client.get("/api/skills")).json()
    [item] = listing["skills"]
    assert item["status"] == "draft" and item["approved"] is False

    # Running before approval is refused.
    async with app.state.services.db.sessionmaker() as session:
        skill = await session.get(Skill, uuid.UUID(item["id"]))
        assert skill is not None
        with pytest.raises(skills.SkillError):
            await skills.queue_run(session, skill, {"amount": 1})

    detail = (await client.get(f"/api/skills/{item['id']}")).json()
    assert detail["code"] == CODE
    wrong = await client.post(f"/api/skills/{item['id']}/approve", json={"code_sha256": "0" * 64})
    assert wrong.status_code == 409
    ok = await client.post(
        f"/api/skills/{item['id']}/approve", json={"code_sha256": detail["code_sha256"]}
    )
    assert ok.status_code == 200 and ok.json()["approved"] is True
    async with app.state.services.db.sessionmaker() as session:
        actions = list(await session.scalars(select(AuditLog.action)))
    assert "skills.approve" in actions

    # Now the chat runs it through the worker (here a fake sandbox, worker switched on).
    app.state.services.settings.skill_worker = True
    sandbox = FakeSandbox()

    async def worker() -> None:
        for _ in range(200):
            if await run_once(app.state.services.db, sandbox, "test-worker"):
                return
            await asyncio.sleep(0.05)

    fake_anthropic.replies = [
        json.dumps({"amount": 50_000_000, "months": 24, "rate": 22}),
        "Oylik to'lov taxminan 2,6 mln so'm.",
    ]
    task = asyncio.create_task(worker())
    events = await stream_chat(client, message="Kredit kalkulyatori: 50 mln, 24 oy, 22%")
    await task
    assert events[0][1]["agent"] == "skill"
    [(code, data)] = sandbox.calls
    assert code == CODE and data == {"amount": 50_000_000, "months": 24, "rate": 22}
    system = fake_anthropic.requests[-1].system or ""
    assert "returned: {'oylik_tolov': 2593908}" in system

    # New code for the same skill clears the approval; a queued run of old code is refused.
    async with app.state.services.db.sessionmaker() as session:
        skill = await session.get(Skill, uuid.UUID(item["id"]))
        assert skill is not None
        run = await skills.queue_run(session, skill, {"amount": 1, "months": 1, "rate": 1})
        await session.commit()
        await skills.save_draft(
            session, skill.user_id, name="Kredit kalkulyatori", description="v2",
            input_hint="", code=CODE + "\n# v2\n",
        )  # fmt: skip
        await session.commit()
    assert await run_once(app.state.services.db, sandbox, "test-worker")
    async with app.state.services.db.sessionmaker() as session:
        stale = await session.get(SkillRun, run.id)
        assert stale is not None and stale.status == "failed"
        assert "approved code changed" in (stale.error or "")
    assert len(sandbox.calls) == 1
    detail = (await client.get(f"/api/skills/{item['id']}")).json()
    assert detail["status"] == "draft" and detail["approved"] is False


async def test_bad_code_cannot_be_approved_and_non_owner_cannot_approve(
    app: FastAPI, client: AsyncClient
) -> None:
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        assert user is not None
        skill = await skills.save_draft(
            session, user.id, name="Xavfli", description="", input_hint="",
            code="import socket\ndef run(d):\n    return 1\n",
        )  # fmt: skip
        good = await skills.save_draft(
            session, user.id, name="Yaxshi", description="", input_hint="", code=CODE
        )
        await session.commit()
        bad_id, bad_sha, good_id, good_sha = (
            skill.id, skill.code_sha256, good.id, good.code_sha256
        )  # fmt: skip
        is_owner = user.email == app.state.services.settings.owner_email or (
            user.role == "super_admin"
        )
    response = await client.post(f"/api/skills/{good_id}/approve", json={"code_sha256": good_sha})
    if not is_owner:
        assert response.status_code == 403
    await make_owner(app, client)
    response = await client.post(f"/api/skills/{bad_id}/approve", json={"code_sha256": bad_sha})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "checks_failed"


async def test_run_without_worker_says_so(
    app: FastAPI, client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await make_owner(app, client)
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        assert user is not None
        skill = await skills.save_draft(
            session, user.id, name="Kredit kalkulyatori", description="", input_hint="", code=CODE
        )
        await skills.approve(session, skill, skill.code_sha256)
        await session.commit()
    fake_anthropic.replies = [json.dumps({"amount": 1, "months": 1, "rate": 1}), "Ishlamadi."]
    await stream_chat(client, message="Kredit kalkulyatori: 1 so'm, 1 oy, 1%")
    system = fake_anthropic.requests[-1].system or ""
    assert "skill worker is not switched on" in system
