"""The boundary around external orchestration (Ruflo): allowed tools, secret masking, env.

Nothing outside this allow-list may ever be called on an external orchestrator,
whatever a model or a plan asks for. Expanding it requires a code change and a
review (see docs/RUFLO_INTEGRATION_PLAN.md, “Tool allow-list”).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

# Coordination only: no shell, terminal, file-system, git, browser, network or memory tools.
RUFLO_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "swarm_init",
        "swarm_status",
        "swarm_shutdown",
        "agent_spawn",
        "agent_execute",
        "agent_status",
        "agent_list",
        "workflow_create",
        "workflow_run",
        "workflow_status",
        "workflow_pause",
        "workflow_resume",
        "workflow_cancel",
    }
)
_MCP_PREFIX = re.compile(r"^mcp__[a-z0-9_-]+__")

# Environment a child process may inherit. Secrets are passed one by one, never by copying
# the whole environment.
SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "NODE_OPTIONS", "SYSTEMROOT"}
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,}"),  # Anthropic / OpenAI keys
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),  # Google API keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),  # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\btvly-[A-Za-z0-9]{16,}"),  # Tavily
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
)
_URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^:/\s@]+):([^@\s/]+)@")
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)\s*[=:]\s*([^\s'\"]+)"
)
MASK = "[redacted]"


def normalize_tool_name(name: str) -> str:
    """`mcp__ruflo__swarm_init` and `swarm_init` are the same tool."""
    return _MCP_PREFIX.sub("", name.strip())


def is_allowed_tool(name: str) -> bool:
    return normalize_tool_name(name) in RUFLO_TOOL_ALLOWLIST


def redact_secrets(text: str) -> str:
    """Mask API keys, tokens, passwords and connection-string credentials."""
    if not text:
        return text
    text = _URL_PASSWORD.sub(rf"\1:{MASK}@", text)
    text = _ASSIGNMENT.sub(rf"\1={MASK}", text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(MASK, text)
    return text


def child_env(
    extra: Mapping[str, str] | None = None, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    """A minimal environment for an external process: safe keys plus explicit additions only."""
    base = source if source is not None else os.environ
    env = {key: value for key, value in base.items() if key in SAFE_ENV_KEYS}
    env.update(extra or {})
    return env
