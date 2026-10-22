"""Super Admin change proposals. Confirmation grants review intent, never execution."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from ezo_api.api.deps import ServicesDep, SessionDep, SuperAdminUser, rate_limit
from ezo_api.db.models import AuditLog, KnowledgeLibrary, LearnedSource
from ezo_api.learning.analyzer import CapabilityAnalyzer
from ezo_api.learning.drafts import MAX_BYTES, validate_draft
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/admin/governance/improvements",
    tags=["governance"],
    dependencies=[Depends(rate_limit("default"))],
)


def _utf8_size(value: str) -> int:
    # PostgreSQL JSONB rejects NUL even when JSON-escaped; reject consistently on
    # SQLite too, before constructing an immutable audit snapshot.
    if "\x00" in value:
        raise ValueError("Proposal text must not contain NUL.")
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Proposal text must contain valid Unicode scalar values.") from exc


class ProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    library_id: uuid.UUID
    goal: str = Field(min_length=1, max_length=1000)

    @field_validator("goal")
    @classmethod
    def unicode_text(cls, value: str) -> str:
        _utf8_size(value)
        return value


class ConfirmationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["request_independent_review", "reject"]
    confirm: Literal[True]


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    language: Literal["python"] = "python"
    source: str = Field(min_length=1, max_length=MAX_BYTES)
    purpose: str = Field(min_length=1, max_length=1000)

    @field_validator("source", "purpose")
    @classmethod
    def source_bytes(cls, value: str) -> str:
        if _utf8_size(value) > MAX_BYTES:
            raise ValueError("Draft exceeds UTF-8 byte limit.")
        return value


class DraftDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["request_independent_review", "reject"]
    confirm: Literal[True]


@router.post("/{proposal_id}/drafts", status_code=201)
async def create_draft(
    proposal_id: uuid.UUID,
    body: DraftIn,
    admin: SuperAdminUser,
    session: SessionDep,
) -> dict[str, Any]:
    proposal = await session.scalar(
        select(AuditLog).where(
            AuditLog.id == proposal_id,
            AuditLog.user_id == admin.id,
            AuditLog.action == "governance.proposal",
        )
    )
    if proposal is None:
        raise HTTPException(404, detail="Proposal not found.")
    if proposal.details["sha256"] != body.proposal_sha256:
        raise HTTPException(409, detail={"code": "proposal_changed"})
    payload = {
        "proposal_id": str(proposal_id),
        **body.model_dump(),
        "validation": validate_draft(body.source),
        "status": "untrusted_draft",
        "execution_authorized": False,
        "merge_authorized": False,
        "deployment_authorized": False,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    draft_id = uuid.uuid4()
    session.add(
        AuditLog(
            id=draft_id,
            user_id=admin.id,
            action="governance.skill_draft",
            target_type="improvement",
            target_id=str(proposal_id),
            details={"sha256": digest, "draft": payload},
        )
    )
    await session.commit()
    return {"id": str(draft_id), "sha256": digest, **payload}


@router.get("/{proposal_id}/drafts")
async def list_drafts(
    proposal_id: uuid.UUID,
    admin: SuperAdminUser,
    session: SessionDep,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
) -> list[dict[str, Any]]:
    proposal = await session.scalar(
        select(AuditLog.id).where(
            AuditLog.id == proposal_id,
            AuditLog.user_id == admin.id,
            AuditLog.action == "governance.proposal",
        )
    )
    if proposal is None:
        raise HTTPException(404, detail="Proposal not found.")
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id == admin.id,
                AuditLog.action == "governance.skill_draft",
                AuditLog.target_id == str(proposal_id),
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [{"id": str(row.id), **row.details} for row in rows]


@router.post("/{proposal_id}/drafts/{draft_id}/decision")
async def decide_draft(
    proposal_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftDecisionIn,
    admin: SuperAdminUser,
    session: SessionDep,
) -> dict[str, Any]:
    draft = await session.scalar(
        select(AuditLog).where(
            AuditLog.id == draft_id,
            AuditLog.user_id == admin.id,
            AuditLog.action == "governance.skill_draft",
            AuditLog.target_id == str(proposal_id),
        )
    )
    if draft is None:
        raise HTTPException(404, detail="Draft not found.")
    if draft.details["sha256"] != body.draft_sha256:
        raise HTTPException(409, detail={"code": "draft_changed"})
    result = {
        "proposal_id": str(proposal_id),
        "draft_id": str(draft_id),
        "sha256": body.draft_sha256,
        "decision": body.decision,
        "sandbox_tested": False,
        "execution_authorized": False,
        "merge_authorized": False,
        "deployment_authorized": False,
    }
    audit(session, admin.id, "governance.draft_decision", "skill_draft", draft_id, result)
    await session.commit()
    return result


@router.post("", status_code=201)
async def propose(
    body: ProposalIn,
    admin: SuperAdminUser,
    session: SessionDep,
    services: ServicesDep,
) -> dict[str, Any]:
    library = await session.scalar(
        select(KnowledgeLibrary).where(
            KnowledgeLibrary.id == body.library_id, KnowledgeLibrary.user_id == admin.id
        )
    )
    if library is None:
        raise HTTPException(404, detail="Library not found.")
    count = await session.scalar(
        select(func.count())
        .select_from(LearnedSource)
        .where(LearnedSource.library_id == library.id, LearnedSource.user_id == admin.id)
    )
    if (count or 0) > 10:
        raise HTTPException(
            422,
            detail={
                "code": "proposal_limit",
                "message": "Select a library with at most ten sources.",
            },
        )
    report = await CapabilityAnalyzer(registered_tools=services.tools.names()).analyze_library(
        session, library
    )
    # A capability report is an evidence-graded proposal, never a tested skill.
    # Keep a bounded immutable snapshot; no generated source, tool or shell call.
    payload = {
        "goal": body.goal,
        "library_id": str(library.id),
        "analysis": report.model_dump(mode="json"),
        "status": "proposal_only",
        "execution_authorized": False,
        "sandbox_tested": False,
        "required_gates": [
            "reviewed_k4_sandbox",
            "isolated_regression_tests",
            "independent_review",
            "explicit_owner_merge_approval",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 32000:
        raise HTTPException(
            422,
            detail={
                "code": "proposal_limit",
                "message": "Select a smaller library for a bounded proposal.",
            },
        )
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    proposal_id = uuid.uuid4()
    session.add(
        AuditLog(
            id=proposal_id,
            user_id=admin.id,
            action="governance.proposal",
            target_type="improvement",
            target_id=str(proposal_id),
            details={"sha256": digest, "proposal": payload},
        )
    )
    await session.commit()
    return {"id": str(proposal_id), "sha256": digest, **payload}


@router.get("")
async def proposals(
    admin: SuperAdminUser,
    session: SessionDep,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == admin.id, AuditLog.action == "governance.proposal")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [{"id": str(r.id), **r.details} for r in rows]


@router.post("/{proposal_id}/decision")
async def decide(
    proposal_id: uuid.UUID,
    body: ConfirmationIn,
    admin: SuperAdminUser,
    session: SessionDep,
) -> dict[str, Any]:
    proposal = await session.scalar(
        select(AuditLog).where(
            AuditLog.id == proposal_id,
            AuditLog.user_id == admin.id,
            AuditLog.action == "governance.proposal",
        )
    )
    if proposal is None:
        raise HTTPException(404, detail="Proposal not found.")
    if proposal.details["sha256"] != body.proposal_sha256:
        raise HTTPException(
            409,
            detail={
                "code": "proposal_changed",
                "message": "Confirm the exact proposal hash being reviewed.",
            },
        )
    audit(
        session,
        admin.id,
        "governance.proposal_decision",
        "improvement",
        proposal_id,
        {"sha256": body.proposal_sha256, "decision": body.decision, "execution_authorized": False},
    )
    await session.commit()
    return {
        "proposal_id": str(proposal_id),
        "decision": body.decision,
        "execution_authorized": False,
        "merge_authorized": False,
        "deployment_authorized": False,
        "sandbox_tested": False,
    }
