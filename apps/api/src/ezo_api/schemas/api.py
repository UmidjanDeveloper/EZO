"""Pydantic request/response schemas for the HTTP API.

Keep in sync with packages/shared/src/types.ts (the web client types).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LanguageCode = Literal["uz", "en", "ru"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- users -----------------------------------------------------------------


class Preferences(BaseModel):
    ui_language: LanguageCode = "uz"
    response_language: Literal["auto", "uz", "en", "ru"] = "auto"
    humor: Literal["default", "off", "light", "normal"] = "default"
    auto_memory: bool = True


class PreferencesUpdate(BaseModel):
    ui_language: LanguageCode | None = None
    response_language: Literal["auto", "uz", "en", "ru"] | None = None
    humor: Literal["default", "off", "light", "normal"] | None = None
    auto_memory: bool | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    preferences: Preferences


# --- projects --------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


# --- conversations ---------------------------------------------------------


class ConversationOut(ORMModel):
    id: uuid.UUID
    title: str
    project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    language: str | None
    agent: str | None
    agent_run_id: uuid.UUID | None
    metadata: dict[str, Any]
    created_at: datetime


# --- chat ------------------------------------------------------------------


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    agent: str | None = Field(default=None, max_length=50, description="Manual agent override")
    channel: Literal["text", "voice"] = Field(
        default="text", description="'voice' when the user speaks and hears the reply"
    )
    speech_seconds: float | None = Field(
        default=None,
        ge=0,
        le=600,
        description="Measured speaking time of a voice message (used by the Language Coach)",
    )


class ChatOut(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut
    run_id: uuid.UUID
    agent: str
    requested_agent: str
    intent: str
    language: str


# --- memory ----------------------------------------------------------------


class MemoryCreate(BaseModel):
    content: str = Field(min_length=2, max_length=1000)
    memory_type: Literal["profile", "project"] = "profile"
    category: Literal["preference", "personal", "goal", "learning", "decision", "fact"] = "fact"
    project_id: uuid.UUID | None = None
    importance: float = Field(default=0.7, ge=0, le=1)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=2, max_length=1000)
    importance: float | None = Field(default=None, ge=0, le=1)
    category: Literal["preference", "personal", "goal", "learning", "decision", "fact"] | None = (
        None
    )


class MemoryOut(ORMModel):
    id: uuid.UUID
    memory_type: str
    category: str
    content: str
    project_id: uuid.UUID | None
    source: str
    source_conversation_id: uuid.UUID | None
    confidence: float
    importance: float
    sensitive: bool
    last_accessed: datetime | None
    created_at: datetime
    updated_at: datetime


# --- observability ---------------------------------------------------------


class AgentRunOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    status: str
    intent: str | None
    intent_confidence: float | None
    agent: str | None
    language: str | None
    route: str | None
    provider: str | None
    model: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    steps: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


# --- system ----------------------------------------------------------------


class ProviderStatus(BaseModel):
    name: str
    display_name: str
    configured: bool
    capabilities: list[str]


class AgentInfo(BaseModel):
    key: str
    names: dict[str, str]
    description: str
    available: bool
    maturity: str
    """planned | experimental | alpha | beta | stable (see ezo_api/maturity.py)."""
    phase: str
    """Roadmap section (ROADMAP.md)."""


class FeatureInfo(BaseModel):
    key: str
    name: str
    phase: str
    maturity: str
    note: str


class SystemStatus(BaseModel):
    version: str
    environment: str
    database: str
    offline_mode: bool
    providers: list[ProviderStatus]
    routing: dict[str, Any]
    agents: list[AgentInfo]
    features: list[FeatureInfo]
    personality: dict[str, Any]
    debug_traces: bool
