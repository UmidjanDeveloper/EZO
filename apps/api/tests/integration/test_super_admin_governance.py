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
