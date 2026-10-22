"""Backend RBAC, immutable source identity and non-authorizing review intent."""

import uuid

from sqlalchemy import select

from ezo_api.db.models import AuditLog, User


async def proposal(client, app):
    await client.get("/api/personal/profile")
    async with app.state.services.db.sessionmaker() as session:
        user = await session.scalar(select(User))
        user.role = "super_admin"
        await session.commit()
    library = await client.post("/api/learning/libraries", json={"name": "Skill sources"})
    result = await client.post(
        "/api/admin/governance/improvements",
        json={"library_id": library.json()["id"], "goal": "Draft a pure calculation"},
    )
    assert result.status_code == 201, result.text
    return result.json()


async def test_normal_user_cannot_create_list_or_review_drafts(client):
    prefix = f"/api/admin/governance/improvements/{uuid.uuid4()}/drafts"
    assert (await client.post(prefix, json={})).status_code == 403
    assert (await client.get(prefix)).status_code == 403
    assert (await client.post(f"{prefix}/{uuid.uuid4()}/decision", json={})).status_code == 403


async def test_draft_validation_persistence_and_hash_bound_review(client, app):
    p = await proposal(client, app)
    prefix = f"/api/admin/governance/improvements/{p['id']}/drafts"
    body = {"proposal_sha256": p["sha256"], "purpose": "Calculate", "source": "x = 1 + 2"}
    assert (await client.post(prefix, json={**body, "execute": True})).status_code == 422
    assert (
        await client.post(prefix, json={**body, "proposal_sha256": "0" * 64})
    ).status_code == 409
    response = await client.post(prefix, json=body)
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["validation"]["static_status"] == "passed_static_only"
    assert draft["execution_authorized"] is False
    saved = (await client.get(prefix)).json()[0]
    assert saved["draft"]["source"] == body["source"]
    assert saved["sha256"] == draft["sha256"]
    assert (await client.get(prefix + "?offset=100")).json() == []
    decision = {
        "draft_sha256": draft["sha256"],
        "decision": "request_independent_review",
        "confirm": True,
    }
    path = f"{prefix}/{draft['id']}/decision"
    assert (await client.post(path, json={**decision, "draft_sha256": "0" * 64})).status_code == 409
    assert (await client.post(path, json={**decision, "confirm": False})).status_code == 422
    reviewed = await client.post(path, json=decision)
    assert reviewed.status_code == 200, reviewed.text
    assert not any(
        reviewed.json()[k]
        for k in (
            "sandbox_tested",
            "execution_authorized",
            "merge_authorized",
            "deployment_authorized",
        )
    )
    async with app.state.services.db.sessionmaker() as session:
        row = await session.scalar(
            select(AuditLog).where(AuditLog.action == "governance.draft_decision")
        )
        assert row.details["sha256"] == draft["sha256"]


async def test_rejected_draft_stays_untrusted_and_unicode_bytes_are_bounded(client, app):
    p = await proposal(client, app)
    prefix = f"/api/admin/governance/improvements/{p['id']}/drafts"
    body = {"proposal_sha256": p["sha256"], "purpose": "Test", "source": "import os"}
    response = await client.post(prefix, json=body)
    assert response.status_code == 201
    assert response.json()["validation"]["static_status"] == "rejected"
    assert response.json()["status"] == "untrusted_draft"
    assert (await client.post(prefix, json={**body, "source": "😀" * 5000})).status_code == 422
    other = f"/api/admin/governance/improvements/{uuid.uuid4()}/drafts"
    assert (await client.post(other, json=body)).status_code == 404
    assert (await client.get(other)).status_code == 404
    # Ownership is checked in addition to platform role.
    async with app.state.services.db.sessionmaker() as session:
        row = await session.get(AuditLog, uuid.UUID(p["id"]))
        foreign = User(email=f"foreign-{uuid.uuid4()}@example.com", display_name="Foreign")
        session.add(foreign)
        await session.flush()
        row.user_id = foreign.id
        await session.commit()
    assert (await client.post(prefix, json=body)).status_code == 404
    assert (await client.get(prefix)).status_code == 404
