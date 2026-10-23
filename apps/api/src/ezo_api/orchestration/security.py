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

# Ruflo's own opt-outs, always set for the Ruflo process (audit: docs/OPEN_SOURCE_AUDIT.md § 6):
# no self-update/auto-install, no background daemon, no promo/telemetry fetches, no rewriting
# of ~/.claude/helpers, and its MCP policy gate + audit log switched on as a second fence.
RUFLO_HARDENING_ENV: dict[str, str] = {
    "CLAUDE_FLOW_AUTO_UPDATE": "false",
    "RUFLO_DAEMON_AUTOSTART": "0",
    "RUFLO_DAEMON_AI_WORKERS": "0",
    "RUFLO_FUNNEL": "0",
    "RUFLO_FUNNEL_MESSAGES": "0",
    "RUFLO_HELPERS_LOCKED": "1",
    "RUFLO_MCP_ENFORCE_POLICY": "1",
    "CLAUDE_FLOW_STRICT_GUARDRAIL": "true",
}
# Tools that are dangerous in Ruflo and must never be reachable, even if a future allow-list
# edit is careless (checked in addition to the allow-list).
RUFLO_TOOL_DENYLIST: frozenset[str] = frozenset(
    {
        "terminal_execute",
        "terminal_create",
        "github_pr_manage",
        "github_issue_track",
        "github_workflow",
        "http_fetch",
        "browser_eval",
        "hooks_codemod",
        "memory_import_claude",
        "managed_agent_create",
        "config_set",
        "config_import",
        "system_reset",
        "mcp_start",
        "mcp_stop",
        "autopilot_enable",
        "transfer_store-download",
        "transfer_ipfs-resolve",
    }
)

# Environment a child process may inherit. Secrets are passed one by one, never by copying
# the whole environment. NODE_OPTIONS is excluded: it can make Node load arbitrary code
# (--require/--import) into the orchestrator process.
SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "SYSTEMROOT"}
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
    tool = normalize_tool_name(name)
    return tool in RUFLO_TOOL_ALLOWLIST and tool not in RUFLO_TOOL_DENYLIST


def redact_secrets(text: str) -> str:
    """Mask API keys, tokens, passwords and connection-string credentials."""
    if not text:
        return text
    text = _URL_PASSWORD.sub(rf"\1:{MASK}@", text)
    text = _ASSIGNMENT.sub(rf"\1={MASK}", text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(MASK, text)
    return text


def ruflo_env(home: str, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for the Ruflo MCP process: minimal, hardened, with an isolated HOME.

    Ruflo writes to ``~/.claude``, ``~/.claude-flow`` and ``~/.ruflo``; a per-mission HOME keeps
    that away from the real user profile. No EZO secret is included.
    """
    return child_env({**RUFLO_HARDENING_ENV, "HOME": home, **(extra or {})})


def child_env(
    extra: Mapping[str, str] | None = None, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    """A minimal environment for an external process: safe keys plus explicit additions only."""
    base = source if source is not None else os.environ
    env = {key: value for key, value in base.items() if key in SAFE_ENV_KEYS}
    env.update(extra or {})
    return env
