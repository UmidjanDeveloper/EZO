"""Shared column helpers for models."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")
"""JSON on SQLite, JSONB on PostgreSQL."""
