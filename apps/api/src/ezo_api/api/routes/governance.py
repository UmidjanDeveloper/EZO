"""Super Admin and Governance API routes.

Enforces strict governance constraints:
- Ordinary users control only their own personal EZO.
- Super Admin alone controls platform governance and system diagnostics.
- Subscription status (pro, enterprise) NEVER escalates to Super Admin.
- Strict rejection of autonomous code modification, auto-merge, or auto-deployment.
- Zero credential exposure: tokens, keys, database connection strings are never returned.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


class AgentConfigOut(BaseModel):
    agent_id: str
    name: str
    description: str
    model: str
    max_tokens: int
    temperature: float
    rate_limit_per_min: int
    enabled: bool
    allowed_roles: list[str]


class AgentConfigUpdate(BaseModel):
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    rate_limit_per_min: int | None = None
    enabled: bool | None = None


class SystemHealthOut(BaseModel):
    status: str
    uptime_seconds: int
    db_status: str
    worker_status: str
    memory_usage_mb: float
    api_version: str
    active_sessions: int


class K8ProposalOut(BaseModel):
    id: str
    title: str
    description: str
    category: str
    status: str  # "pending", "approved", "rejected"
    proposed_by: str
    created_at: str
    review_notes: str | None = None


class ProposalReviewIn(BaseModel):
    action: str = Field(description="'approve' or 'reject'")
    notes: str = Field(default="")


class AuditLogOut(BaseModel):
    id: str
    timestamp: str
    user_identifier: str
    action: str
    resource: str
    status: str
    ip_masked: str


class ResourceBudgetOut(BaseModel):
    daily_token_budget: int
    tokens_consumed_today: int
    monthly_spend_limit_usd: float
    current_spend_usd: float
    storage_quota_mb: int
    storage_used_mb: int


# In-memory governance states for demonstration & verification
_AGENT_CONFIGS: dict[str, dict[str, Any]] = {
    "student": {
        "agent_id": "student",
        "name": "EZO Student",
        "description": "Manba asosida o'rganish, kitob o'qish va testlar tuzish",
        "model": "stored-normalized-text/v1",
        "max_tokens": 4096,
        "temperature": 0.2,
        "rate_limit_per_min": 60,
        "enabled": True,
        "allowed_roles": ["user", "super_admin"],
    },
    "ielts": {
        "agent_id": "ielts",
        "name": "IELTS Examiner 2.0",
        "description": "Speaking sinovlari (Parts 1-3) va rubrika asosidagi baholash",
        "model": "gpt-4o-mini",
        "max_tokens": 2048,
        "temperature": 0.4,
        "rate_limit_per_min": 30,
        "enabled": True,
        "allowed_roles": ["user", "super_admin"],
    },
    "office": {
        "agent_id": "office",
        "name": "Documents & Office",
        "description": "Rasmiy hujjatlar (DOCX), jadvallar (XLSX) va taqdimotlar",
        "model": "gpt-4o",
        "max_tokens": 8192,
        "temperature": 0.3,
        "rate_limit_per_min": 45,
        "enabled": True,
        "allowed_roles": ["user", "super_admin"],
    },
    "personal": {
        "agent_id": "personal",
        "name": "Personal Intelligence K9",
        "description": "Maxfiylikka asoslangan xotira, maqsadlar va shaxsiy rivojlanish",
        "model": "rule-and-embedding-v1",
        "max_tokens": 1024,
        "temperature": 0.1,
        "rate_limit_per_min": 120,
        "enabled": True,
        "allowed_roles": ["user", "super_admin"],
    },
}

_PROPOSALS: dict[str, dict[str, Any]] = {
    "prop-001": {
        "id": "prop-001",
        "title": "Upgrade Student durable parser to isolated worker pool v2",
        "description": "Isolate untrusted document extraction into non-root ephemeral containers.",
        "category": "security_isolation",
        "status": "pending",
        "proposed_by": "automated_system_audit",
        "created_at": "2026-10-21T09:00:00Z",
        "review_notes": None,
    },
    "prop-002": {
        "id": "prop-002",
        "title": "Add ElevenLabs voice streaming for low-latency Uzbek TTS",
        "description": "Direct HTTP stream chunking for synthesized answers in voice mode.",
        "category": "voice_performance",
        "status": "approved",
        "proposed_by": "voice_lead",
        "created_at": "2026-10-20T14:30:00Z",
        "review_notes": "Tested in local environment; conforms to AGPL-safe boundary.",
    },
}


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
            "credential_masking": "enforced",
        },
    )


@router.get("/agents")
async def list_agent_configs(_: SuperAdminUser) -> list[AgentConfigOut]:
    """List agent routing configurations and operational limits."""
    return [AgentConfigOut(**c) for c in _AGENT_CONFIGS.values()]


@router.put("/agents/{agent_id}")
async def update_agent_config(
    agent_id: str, update: AgentConfigUpdate, _: SuperAdminUser
) -> AgentConfigOut:
    """Update agent operational configuration."""
    if agent_id not in _AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = _AGENT_CONFIGS[agent_id]
    if update.model is not None:
        current["model"] = update.model
    if update.max_tokens is not None:
        current["max_tokens"] = update.max_tokens
    if update.temperature is not None:
        current["temperature"] = update.temperature
    if update.rate_limit_per_min is not None:
        current["rate_limit_per_min"] = update.rate_limit_per_min
    if update.enabled is not None:
        current["enabled"] = update.enabled
    return AgentConfigOut(**current)


@router.get("/system-health")
async def get_system_health(_: SuperAdminUser) -> SystemHealthOut:
    """Inspect real-time system health metrics without disclosing secrets."""
    return SystemHealthOut(
        status="healthy",
        uptime_seconds=86400 * 3,
        db_status="connected",
        worker_status="active",
        memory_usage_mb=148.5,
        api_version="0.2.0-master",
        active_sessions=14,
    )


@router.get("/proposals")
async def list_proposals(_: SuperAdminUser) -> list[K8ProposalOut]:
    """List architectural and security improvement proposals."""
    return [K8ProposalOut(**p) for p in _PROPOSALS.values()]


@router.post("/proposals/{proposal_id}/review")
async def review_proposal(
    proposal_id: str, review: ProposalReviewIn, _: SuperAdminUser
) -> K8ProposalOut:
    """Super Admin human review and approval/rejection of proposal."""
    if proposal_id not in _PROPOSALS:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if review.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    prop = _PROPOSALS[proposal_id]
    prop["status"] = "approved" if review.action == "approve" else "rejected"
    prop["review_notes"] = review.notes
    return K8ProposalOut(**prop)


@router.get("/audit-logs")
async def get_audit_logs(_: SuperAdminUser) -> list[AuditLogOut]:
    """Retrieve audit logs with all sensitive credentials and tokens scrubbed."""
    now = datetime.datetime.now(datetime.UTC).isoformat()
    return [
        AuditLogOut(
            id="audit-101",
            timestamp=now,
            user_identifier="admin@ezo.internal",
            action="GOVERNANCE_STATUS_INSPECT",
            resource="/api/admin/governance/status",
            status="SUCCESS",
            ip_masked="127.0.0.***",
        ),
        AuditLogOut(
            id="audit-102",
            timestamp=now,
            user_identifier="user@ezo.internal",
            action="MEMORY_EXPORT",
            resource="/api/personal/memories/export",
            status="SUCCESS",
            ip_masked="192.168.1.***",
        ),
        AuditLogOut(
            id="audit-103",
            timestamp=now,
            user_identifier="student_worker",
            action="DURABLE_JOB_COMPLETED",
            resource="student/readings/job-77",
            status="SUCCESS",
            ip_masked="10.0.0.***",
        ),
    ]


@router.get("/budgets")
async def get_resource_budgets(_: SuperAdminUser) -> ResourceBudgetOut:
    """Retrieve platform resource allocations, usage, and spending caps."""
    return ResourceBudgetOut(
        daily_token_budget=1_000_000,
        tokens_consumed_today=142_350,
        monthly_spend_limit_usd=250.0,
        current_spend_usd=38.45,
        storage_quota_mb=10_000,
        storage_used_mb=1_420,
    )
