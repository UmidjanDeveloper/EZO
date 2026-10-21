"""Super Admin and Governance API routes.

Enforces strict governance constraints:
- Ordinary users control only their own personal EZO.
- Super Admin alone controls platform governance and system diagnostics.
- Subscription status (pro, enterprise) NEVER escalates to Super Admin.
- Strict rejection of autonomous code modification, auto-merge, or auto-deployment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ezo_api.agents.registry import AgentRegistry
from ezo_api.api.deps import SuperAdminUser, rate_limit

router = APIRouter(
    prefix="/api/admin/governance",
    tags=["governance"],
    dependencies=[Depends(rate_limit("default"))],
)


class GovernanceStatusOut(BaseModel):
    role: str
    super_admin_verified: bool
    autonomous_code_modification: bool = False
    autonomous_pr_merge: bool = False
    autonomous_deployment: bool = False
    governance_mode: str = "human_governed"
    policies: dict[str, Any]


@router.get("/status")
async def get_governance_status(admin_user: SuperAdminUser) -> GovernanceStatusOut:
    """Diagnostic and platform governance status. Strictly restricted to Super Admin role."""
    return GovernanceStatusOut(
        role=admin_user.role,
        super_admin_verified=True,
        autonomous_code_modification=False,
        autonomous_pr_merge=False,
        autonomous_deployment=False,
        governance_mode="human_governed",
        policies={
            "tenant_isolation": "enforced",
            "memory_opt_in": "enforced",
            "subscription_privilege_escalation": "blocked",
            "k8_autonomous_modification": "disabled",
        },
    )
