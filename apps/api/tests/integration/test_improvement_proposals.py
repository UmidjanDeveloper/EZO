"""Proposals and owner decisions never confer action authority."""

import uuid

from sqlalchemy import select

from ezo_api.db.models import AuditLog, User


async def admin(client, app):
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        user.role = "super_admin"
        await session.commit()


async def test_normal_and_subscription_users_cannot_propose_or_confirm(client, app):
    body = {"library_id": str(uuid.uuid4()), "goal": "Improve grounded answers"}
    assert (await client.post("/api/admin/governance/improvements", json=body)).status_code == 403
    assert (await client.get("/api/admin/governance/improvements")).status_code == 403
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        user.preferences = {"subscription": "enterprise"}
        await session.commit()
    assert (await client.post("/api/admin/governance/improvements", json=body)).status_code == 403
    r = await client.post(
        "/api/admin/governance/improvements/" + str(uuid.uuid4()) + "/decision",
        json={
            "proposal_sha256": "a" * 64,
            "decision": "request_independent_review",
            "confirm": True,
        },
    )
    assert r.status_code == 403


async def test_owner_proposal_hash_bound_confirmation_is_not_execution(client, app):
    await admin(client, app)
    library = await client.post("/api/learning/libraries", json={"name": "Reviewed sources"})
    assert library.status_code == 201, library.text
    proposal = await client.post(
        "/api/admin/governance/improvements",
        json={"library_id": library.json()["id"], "goal": "Improve citation coverage"},
    )
    assert proposal.status_code == 201, proposal.text
    p = proposal.json()
    assert p["status"] == "proposal_only" and p["sandbox_tested"] is False
    assert p["execution_authorized"] is False
    path = "/api/admin/governance/improvements/" + p["id"] + "/decision"
    body = {
        "proposal_sha256": p["sha256"],
        "decision": "request_independent_review",
        "confirm": True,
    }
    assert (await client.post(path, json={**body, "proposal_sha256": "0" * 64})).status_code == 409
    assert (await client.post(path, json={**body, "confirm": False})).status_code == 422
    r = await client.post(path, json=body)
    assert r.status_code == 200, r.text
    assert not any(
        r.json()[k] for k in ["execution_authorized", "merge_authorized", "deployment_authorized"]
    )
    rows = (await client.get("/api/admin/governance/improvements")).json()
    assert rows[0]["id"] == p["id"] and rows[0]["sha256"] == p["sha256"]
    # The list has the create response's flat shape plus the recorded decision.
    assert rows[0]["goal"] == p["goal"] and rows[0]["status"] == "proposal_only"
    assert rows[0]["decision"] == body["decision"]
    assert rows[0]["execution_authorized"] is False
    async with app.state.services.db.sessionmaker() as session:
        records = (
            await session.scalars(
                select(AuditLog).where(AuditLog.action == "governance.proposal_decision")
            )
        ).all()
        assert len(records) == 1 and records[0].details["sha256"] == p["sha256"]
    # A proposal offers no public execution, installation or push route.
    for suffix in ["execute", "install", "push", "merge", "deploy"]:
        assert (
            await client.post(
                "/api/admin/governance/improvements/" + p["id"] + "/" + suffix, json={}
            )
        ).status_code == 404


async def test_foreign_library_and_unknown_fields_rejected(client, app):
    await admin(client, app)
    base = {"library_id": str(uuid.uuid4()), "goal": "Upgrade"}
    assert (await client.post("/api/admin/governance/improvements", json=base)).status_code == 404
    assert (
        await client.post("/api/admin/governance/improvements", json={**base, "execute": True})
    ).status_code == 422
