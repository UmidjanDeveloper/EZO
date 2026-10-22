"""Integration tests for Super Admin and Governance security constraints.

Verifies:
- Ordinary users control only their own personal EZO.
- Super Admin alone controls global platform governance.
- Subscription status (pro, enterprise) NEVER grants Super Admin permissions.
- Autonomous code modification and autonomous PR merge are strictly blocked.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from ezo_api.db.models import User


@pytest.mark.asyncio
async def test_ordinary_user_cannot_access_governance(client: AsyncClient) -> None:
    # First make a call to ensure user is provisioned in local auth mode
    init_res = await client.get("/api/personal/profile")
    assert init_res.status_code == 200

    # Default user has role="user"
    resp = await client.get("/api/admin/governance/status")
    assert resp.status_code == 403
    data = resp.json()
    assert "Super Admin privileges required" in data["error"]["message"]


@pytest.mark.asyncio
async def test_subscription_upgrade_does_not_grant_super_admin(
    app: FastAPI, client: AsyncClient
) -> None:
    # Ensure user is provisioned
    await client.get("/api/personal/profile")

    sessionmaker = app.state.services.db.sessionmaker
    async with sessionmaker() as session:
        users = (await session.scalars(select(User))).all()
        assert users
        user = users[0]
        user.preferences = {"subscription": "enterprise", "plan": "pro_unlimited"}
        user.role = "user"
        await session.commit()

    # Verify user is still role="user" and blocked from governance
    resp = await client.get("/api/admin/governance/status")
    assert resp.status_code == 403
    data = resp.json()
    assert "Subscription status does not grant governance access" in data["error"]["message"]


@pytest.mark.asyncio
async def test_super_admin_can_access_governance(app: FastAPI, client: AsyncClient) -> None:
    # Ensure user is provisioned
    await client.get("/api/personal/profile")

    sessionmaker = app.state.services.db.sessionmaker
    async with sessionmaker() as session:
        users = (await session.scalars(select(User))).all()
        assert users
        user = users[0]
        user.role = "super_admin"
        await session.commit()

    resp = await client.get("/api/admin/governance/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "super_admin"
    assert data["super_admin_verified"] is True
    assert data["autonomous_code_modification"] is False
    assert data["autonomous_pr_merge"] is False
    assert data["policies"]["subscription_privilege_escalation"] == "blocked"
    assert data["policies"]["k8_autonomous_modification"] == "disabled"


@pytest.mark.asyncio
async def test_super_admin_endpoints_full_lifecycle(app: FastAPI, client: AsyncClient) -> None:
    # Ensure user is provisioned as super_admin
    await client.get("/api/personal/profile")
    sessionmaker = app.state.services.db.sessionmaker
    async with sessionmaker() as session:
        users = (await session.scalars(select(User))).all()
        user = users[0]
        user.role = "super_admin"
        await session.commit()

    # 1. System health
    health_resp = await client.get("/api/admin/governance/system-health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    # 2. Agent settings list and update
    agents_resp = await client.get("/api/admin/governance/agents")
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    assert len(agents) >= 4

    put_resp = await client.put(
        "/api/admin/governance/agents/student",
        json={"rate_limit_per_min": 75, "temperature": 0.25},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["rate_limit_per_min"] == 75

    # 3. K8 proposals list and review
    prop_resp = await client.get("/api/admin/governance/proposals")
    assert prop_resp.status_code == 200
    props = prop_resp.json()
    assert len(props) >= 2

    review_resp = await client.post(
        "/api/admin/governance/proposals/prop-001/review",
        json={"action": "approve", "notes": "Approved after local test suite passed."},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "approved"

    # 4. Audit logs
    audit_resp = await client.get("/api/admin/governance/audit-logs")
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) >= 3
    for log_item in logs:
        assert "password" not in log_item
        assert "secret" not in log_item

    # 5. Resource budgets
    budget_resp = await client.get("/api/admin/governance/budgets")
    assert budget_resp.status_code == 200
    assert budget_resp.json()["daily_token_budget"] == 1_000_000
