"""Schemas for EZO JARVIS Mode & OpenJarvis Local Device Agent.

Defines task plans, execution steps, companion device pairing,
security approval requests, and immutable audit receipts.
"""

from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field


class JarvisStepType(str, enum.Enum):
    LIST_FILES = "companion.list_files"
    READ_FILE = "companion.read_file"
    COMPUTE_PERCENTAGES = "analysis.compute_percentages"
    GENERATE_PDF = "office.generate_pdf"
    PREPARE_TELEGRAM = "telegram.prepare_message"
    REQUEST_APPROVAL = "security.request_approval"
    SEND_TELEGRAM = "telegram.send_message"
    REPORT_VOICE = "voice.report_completion"
    CUSTOM = "custom"


class JarvisStepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JarvisStep(BaseModel):
    id: str
    title: str
    title_uz: str
    type: JarvisStepType
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: JarvisStepStatus = JarvisStepStatus.PENDING
    requires_approval: bool = False
    approval_granted: bool | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    receipt: dict[str, Any] | None = None


class JarvisTaskPlan(BaseModel):
    id: str
    instruction: str
    language: str = "uz"
    status: str = "pending"
    steps: list[JarvisStep] = Field(default_factory=list)
    current_step_id: str | None = None
    created_at: str
    updated_at: str
    receipt: dict[str, Any] | None = None


class JarvisApprovalRequest(BaseModel):
    task_id: str
    step_id: str
    action_type: str
    recipient: str | None = None
    attachment: str | None = None
    summary: str
    summary_uz: str
    approved: bool
    revocable: bool = True


class CompanionDeviceInfo(BaseModel):
    device_id: str
    device_name: str
    os: str = "Windows"
    online: bool = True
    authorized_directories: list[str] = Field(default_factory=lambda: ["Downloads"])
    pairing_status: str = "paired"
    last_heartbeat: str | None = None


class CompanionFileItem(BaseModel):
    filename: str
    path: str
    size_bytes: int
    modified_at: str
    format: str
    sha256: str


class PlanGenerationRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)
    language: str = "uz"
    device_id: str | None = None


class ExecuteStepRequest(BaseModel):
    task_id: str
    step_id: str
    input_overrides: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    comment: str | None = None
