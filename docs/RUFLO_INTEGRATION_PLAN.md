# Ruflo integration plan

> Status (2026-10-17): **architecture prepared, not active.** The `OrchestrationProvider`
> interface and a working `NativeOrchestrationProvider` are in the code
> (`apps/api/src/ezo_api/orchestration/`). Missions are not yet started from chat. Ruflo is
> **not installed, not required and off by default**. External execution through Ruflo is
> scheduled after the roadmap foundations (LanguageCoach, Visual, Video, Government
> knowledge, DeveloperAgent) — see [ROADMAP.md](../ROADMAP.md).
>
> Licence and security audit: [OPEN_SOURCE_AUDIT.md § 6](OPEN_SOURCE_AUDIT.md#6-ruflo).

## 1. What Ruflo is and why EZO would use it

[Ruflo](https://github.com/ruvnet/ruflo) (MIT, by ruvnet; formerly *claude-flow*) is a
multi-agent orchestration toolkit for Claude Code and other coding agents: swarms,
agent lifecycle, workflows, hooks, memory and many plugins, exposed mainly as an MCP
server and a CLI.

EZO already has its own core: EzoCore, providers and routing, memory, knowledge/RAG,
tools, artifacts, story projects, voice and research. What EZO lacks is **coordination of
several specialists on one long job** ("research the market, build the business model,
make the pitch deck and the website"). Ruflo is evaluated *only* for that:

| Ruflo capability | Used by EZO? |
|---|---|
| Swarm coordination, agent lifecycle, workflows, pause/resume | **Candidate** (through the allow-list below) |
| Worktree isolation for parallel coding agents | **Candidate**, DeveloperAgent missions only |
| Observability of runs | Candidate (mapped into EZO's mission timeline) |
| Memory / vector DB / "AgentDB" / learning | **No** — EZO's MemoryService and knowledge base stay authoritative |
| Model providers / routing | **No** — EZO's ModelRouter stays authoritative |
| Hooks that modify the developer's Claude Code settings | **No** |
| Terminal, file, git, browser, network, deploy tools | **No** (never through Ruflo; EZO's own sandboxed tools only) |
| Plugin marketplace / auto-installed mods | **No** |

**Principle:** Ruflo coordinates; EZO does the work. Every agent step still runs through
EZO's agents, providers, tools, policies and audit logs. A user never needs to know that
Ruflo, MCP, swarms or worktrees exist — they just say *“Ezo, shu ishni qilib ber.”*

## 2. Architecture

```
User
 └─ EzoCore (authoritative: language, intent, memory, context, persistence, tracing)
     ├─ complexity check (deterministic, no model call)
     │    ├─ simple  → one agent directly (General, Research, Document, Presentation, …)
     │    └─ mission → OrchestrationProvider
     │                   ├─ NativeOrchestrationProvider   (default, always available)
     │                   └─ RufloProvider                 (optional, off by default)
     │                         └─ MCPClient (stdio, allow-listed tools only)
     │                               └─ Ruflo MCP server (separate process / container)
     └─ agents ← every mission step is executed by an EZO agent via a StepExecutor
```

Code (present today):

| File | Role |
|---|---|
| `orchestration/base.py` | `OrchestrationProvider` interface: `plan_mission`, `start_mission`, `get_status`, `pause`, `resume`, `cancel`, `submit_approval`, `list_agent_runs`, `get_result`; `StepContext`; `StepExecutor` |
| `orchestration/models.py` | `MissionPlan`, `StepSpec` (validated DAG), `AgentOutput` contract, `Mission`, `MissionStep`, `MissionEvent`, `MissionApproval`, `MissionResult` |
| `orchestration/complexity.py` | `assess()` — single agent vs mission; `draft_plan()` — deterministic plan |
| `orchestration/native.py` | `NativeOrchestrationProvider` — the working runner |
| `orchestration/security.py` | Ruflo tool allow-list, secret redaction, minimal child environment |
| `orchestration/registry.py` | `select_orchestration()` — native by default, fallback notice |

No Ruflo-specific type leaves `RufloProvider`. The rest of EZO only knows
`OrchestrationProvider`, `Mission*` and `AgentOutput`.

### Why the native provider exists first

EZO must work fully without Ruflo, and missions must be testable in CI without Node, MCP
or paid APIs. The native runner already does dependency ordering, parallel steps, retries,
timeouts, approval gates, pause/resume/cancel and artifact linking. Ruflo is added later
only where it brings something the native runner lacks (e.g. worktree-isolated coding
swarms), never as a replacement.

## 3. Complexity routing

`orchestration/complexity.py` counts factors from the text — no model call, so routing is
cheap and predictable:

- specialist roles mentioned (research, business, document, presentation, visual,
  developer, legal research); a whole-venture request ("startup") implies the usual team;
- whole-project scope ("boshidan oxirigacha", "to'liq", "end-to-end", "parallel");
- several chained tasks; many items ("20 ta competitor");
- independent code areas (frontend, backend, security, tests, database);
- actions that need approval (push, deploy, publish, send e-mail, delete, pay).

A request becomes a mission only if it has **≥ 2 independent roles or code areas and a
score ≥ 3**. Verified examples (unit tests):

| Request | Result |
|---|---|
| “PDFni qisqartir.” | DocumentAgent directly |
| “Bugungi ob-havo haqida report yoz.” | single agent |
| “Hisobot asosida taqdimot tayyorla” | PresentationAgent directly |
| “20 ta competitorni o‘rgan, biznes model tuz, 15 slayd pitch deck yarat.” | mission |
| “Repo’ni audit qil: frontend/backend/security bo‘yicha parallel analiz, keyin fix qil.” | mission |
| “Ezo, startupimni boshidan oxirigacha tayyorla.” | mission |
| “Ezo, yangi davlat qarorini top, tahlil qil va professional hisobot tayyorla.” | mission |

`draft_plan()` builds a small graph: research first, producers in parallel after it, the
presentation after the business model and report it builds on, one approval-gated change
step for code, and a final QA step that depends on everything. A later version lets the
reasoning model *propose* a plan, but it must still validate as a `MissionPlan`.

## 4. Mission schema

Today these are in-memory types (`orchestration/models.py`). When missions start from chat,
they become tables (one Alembic migration), with the same fields:

| Table | Fields |
|---|---|
| `missions` | id, user_id, project_id (SET NULL), conversation_id (SET NULL), title, goal, status, orchestration_provider, external_run_id (Ruflo), current_step_id, progress, failure_reason, metadata, created_at, started_at, completed_at |
| `mission_steps` | id, mission_id, step_key, step_index, title, description, agent_type, status, dependencies (JSON list of step keys), requires_approval, approval_reason, max_retries, attempts, input (JSON: dependency output ids), output (JSON `AgentOutput`), error, started_at, completed_at |
| `mission_agents` | id, mission_id, step_id, agent_type, provider, model, external_agent_id, status, input_tokens, output_tokens, started_at, finished_at |
| `mission_events` | id, mission_id, step_id, kind, message (redacted), presence, debug (JSON, debug mode only), created_at |
| `mission_approvals` | id, mission_id, step_id, action, reason, what_changes, status (pending/approved/rejected), decided_by, note, decided_at |
| `mission_artifacts` | mission_id, step_id, artifact_id, artifact_version — links to the existing Artifact system |

Statuses — mission: `created`, `planning`, `running`, `waiting_for_user`, `paused`,
`completed`, `failed`, `cancelled`. Step: `pending`, `waiting_for_user`, `running`,
`completed`, `failed`, `rejected`, `skipped`, `cancelled`.

### Agent output contract

Every step returns an `AgentOutput` (Pydantic, validated; free text alone is rejected):

```json
{
  "status": "completed | failed | needs_input",
  "summary": "…",
  "findings": ["…"],
  "artifacts": [{"id": "…", "title": "…", "type": "presentation", "version": 1}],
  "files_changed": ["apps/web/…"],
  "sources": [{"title": "…", "url": "…"}],
  "errors": ["…"],
  "next_recommendation": "…"
}
```

### Shared context (anti-drift)

A step receives a `StepContext`: the mission goal, its own step, and **only the outputs of
the steps it depends on**. It does not receive the whole conversation. EZO's normal agent
pipeline adds the project, relevant memories and retrieved knowledge. Defaults: at most
12 steps, at most 6 agents in parallel (typical missions use 3–6), one owner per step, a
coordinator (EZO) that owns the shared state, and a final QA step.

## 5. Lifecycle

```
created → running ─┬─ (all steps done, none failed) ─────────→ completed
                   ├─ (a step failed after retries) ─────────→ failed  (dependents skipped)
                   ├─ (approval needed) → waiting_for_user ─┬─ approve → running
                   │                                        └─ reject  → running (step rejected,
                   │                                                      dependents skipped)
                   ├─ pause → paused (after the running steps) → resume → running
                   └─ cancel → cancelled (running steps stopped)
```

Rules implemented and tested in the native provider:

- A step starts as soon as all its dependencies are `completed`; independent steps run in
  parallel (capped).
- Failures are retried `max_retries` times. A step that still fails makes the mission
  `failed`, and its dependents — including the final QA — are skipped. **A mission is never
  reported completed when a step or the QA failed.**
- Step timeouts (default 600 s, `EZO_RUFLO_TIMEOUT_SECONDS`) count as failures.
- Output that does not match the contract counts as a failure.
- Errors and events are passed through `redact_secrets()` before they are stored.
- Missions are private to their owner.

## 6. Approval system

Steps that change something outside EZO need a human decision first: pushing Git changes,
deleting files, publishing content, sending e-mail, spending money, deploying
infrastructure, changing external accounts, destructive database actions. The step's
`approval_reason` must say **what will happen, why it is needed and what will change**
(plan validation rejects an approval step without it). The mission goes to
`waiting_for_user`, the orb shows `idle` (EZO is waiting, not working), and the chat shows
an approval card with *Approve* / *Reject*. A decision is recorded once
(`mission_approvals`, audit log). Rejecting skips that step and its dependents but lets
independent work finish.

DeveloperAgent missions add: work happens in isolated Git worktrees on a mission branch;
the coordinator reviews every diff, resolves conflicts and runs lint, typecheck, tests and
the production build; nothing is merged or pushed without approval; never "merge blindly".

## 7. Security boundary

Detailed findings: [OPEN_SOURCE_AUDIT.md § 6](OPEN_SOURCE_AUDIT.md#6-ruflo).

**What the audit changed in this plan.** Ruflo's MCP server exposes about 380 tools,
including `terminal_execute`, which passes model text to `execSync` with the full
environment, as well as GitHub merge/trigger, browser JS and IPFS downloads. Its `init`
pre-approves every `mcp__claude-flow__*` tool, and its plugin adds a `PermissionRequest`
hook that auto-allows them. Its swarm and agent-spawn tools only *record state*; real work
happens in `agent_execute`, which calls `api.anthropic.com` (or `ANTHROPIC_BASE_URL`)
directly with its own key. That leads to these rules:

- EZO **never runs `ruflo init`**, never installs its Claude Code plugin, mods or hooks, and
  never uses `.mcp.json` / `settings.json` generated by Ruflo.
- EZO's own allow-list is the gate, plus a hard **deny-list** (`RUFLO_TOOL_DENYLIST`:
  `terminal_*`, `github_*`, `http_fetch`, `browser_eval`, `hooks_codemod`,
  `memory_import_claude`, `managed_agent_create`, `config_*`, `system_reset`, `mcp_start/stop`,
  `autopilot_enable`, IPFS transfers). Ruflo's own MCP policy gate is switched on as a
  second fence (`RUFLO_MCP_ENFORCE_POLICY=1`, with a matching `.harness/mcp-policy.json` and
  `RUFLO_MCP_AUDIT_LOG_PATH`).
- **Model calls stay in EZO.** If `agent_execute` / `workflow_run` are used, Ruflo gets
  `ANTHROPIC_BASE_URL` pointing to an internal EZO model proxy and a short-lived,
  mission-scoped token as its "API key". It never gets a real provider key. The proxy applies
  EZO routing, cost limits, redaction and audit. Without the proxy, these two tools stay off,
  and Ruflo is used only for bookkeeping (swarm/agent/workflow status), while EZO agents do
  the work.
- The process runs with `ruflo_env()`: a minimal environment, **an isolated per-mission
  `HOME`** (Ruflo writes `~/.claude/helpers`, `~/.claude-flow`, `~/.ruflo` and appends to
  `~/.claude/CLAUDE.md`), and its opt-outs set: `CLAUDE_FLOW_AUTO_UPDATE=false` (no self-update
  or auto-install of patch releases), `RUFLO_DAEMON_AUTOSTART=0`, `RUFLO_DAEMON_AI_WORKERS=0`,
  `RUFLO_FUNNEL=0`, `RUFLO_FUNNEL_MESSAGES=0` (no promo feed), `RUFLO_HELPERS_LOCKED=1`,
  `CLAUDE_FLOW_STRICT_GUARDRAIL=true`.
- **stdio transport only.** Its HTTP transport needs no token on loopback.
- Honest consequence: for document and presentation missions, Ruflo adds little over the
  native runner today. Its value appears with DeveloperAgent missions (parallel coding
  workers, worktrees), which is why the provider is scheduled after that phase.

1. **Separate process.** Ruflo runs as its own process or container, started by EZO's
   `RufloProvider` with an argument list (no shell), never imported into FastAPI. Its
   failures, timeouts or bad output fall back to the native provider; they never crash EZO.
2. **Pinned version.** `EZO_RUFLO_COMMAND` must name an exact, reviewed version (audited:
   `ruflo` 3.56.10, commit `961ab6c`). No `@latest`, no `npx --yes` fallbacks, no automatic
   updates (`CLAUDE_FLOW_AUTO_UPDATE=false`; the CLI flag `--no-update` is honoured from this
   commit on). Preferably installed into the Ruflo container image at build time.
3. **Tool allow-list** (`orchestration/security.py`, `RUFLO_TOOL_ALLOWLIST`). Only
   coordination tools may be called:
   `swarm_init`, `swarm_status`, `swarm_shutdown`, `agent_spawn`, `agent_execute`,
   `agent_status`, `agent_list`, `workflow_create`, `workflow_run`, `workflow_status`,
   `workflow_pause`, `workflow_resume`, `workflow_cancel`.
   Everything else — terminal/shell, file system, git, GitHub, browser, network, memory,
   neural/learning, plugin install, hooks, daemon, deploy — is refused by EZO before any
   call, whatever a plan or a model asks. The MCP client lists the server's tools at start
   and refuses to run if an allow-listed name is missing or its schema changed unexpectedly.
   Expanding the list is a code change with review.
4. **No secrets.** The process gets `ruflo_env()`: `PATH`, an isolated `HOME`, locale, the
   hardening opt-outs and only the variables EZO passes explicitly. (Ruflo itself passes its
   full environment to the child processes it starts, so nothing secret may be in it.) EZO's `.env`, API keys, database URL and tokens are never
   copied. Model calls stay inside EZO (agents run through EZO's router), so Ruflo needs no
   provider keys. All text that leaves or comes back is redacted (`redact_secrets()`).
5. **Working directory.** An empty, per-mission directory under EZO's storage (or an
   approved repository worktree for DeveloperAgent missions). Never the EZO repository, never
   the user's home directory. Ruflo's `init` is not run there.
6. **Network.** In Docker the Ruflo container joins an internal network only (like the
   `voice` profile); no internet unless a reviewed feature needs it.
7. **Limits.** Per-call timeout, per-mission wall-clock limit, maximum agents, maximum
   output size; MCP responses are validated against schemas; oversized or invalid responses
   are errors.
8. **Audit.** Every MCP call is logged like a `ToolCall` (tool name, redacted arguments,
   status, duration). Approvals and cancellations go to the audit log.
9. **No arbitrary shell from user text.** User or model text is never turned into a command
   line. The only command executed is the configured `EZO_RUFLO_COMMAND`, split into an
   argument list once at startup.

## 8. MCP strategy

- A general `MCPClient` (not Ruflo-specific) will live in `ezo_api/mcp/`: start/connect
  (stdio first, streamable HTTP later), `list_tools`, `call_tool`, timeouts, cancellation,
  structured errors, audit logging. Other integrations can reuse it later.
- `RufloProvider(OrchestrationProvider)` translates a validated `MissionPlan` into
  `workflow_create` / `workflow_run`, polls `workflow_status` / `agent_status`, and maps
  Ruflo states to EZO mission states. Each Ruflo agent step calls back into EZO through a
  narrow, authenticated *step execution* endpoint, so the work is still done by EZO agents.
- If anything is off (disabled, not installed, start-up failure, timeout, invalid
  response), `select_orchestration()` returns the native provider with the notice:
  *“Advanced orchestration provider unavailable; continuing with EZO's native workflow.”*

## 9. UI concept

Inside the chat, not a dashboard:

```
EZO is working · 4 / 7 steps
Current: Presentation draft
▸ details
   ✓ Research
   ✓ Competitors
   ✓ Business model
   → Presentation
   ○ Website
   ○ Final QA
```

- Approval requests appear as a clear card: action, why, what will change, *Approve* /
  *Reject*.
- Created files appear as the usual artifact cards; the mission links all of them.
- The orb shows real states from mission events: research → `searching`, reading sources →
  `reading`, documents/presentations/visuals → `creating`, coding → `coding`, other work →
  `working`, waiting for approval → `idle`, done → `completed`, failure → `error`.
- Debug mode (existing setting) shows provider, agents, Ruflo run id, tool calls, tokens,
  timings and failures. Never hidden chain-of-thought.

## 10. Testing strategy

Present today (CI, no Node, no paid API):

- `tests/unit/test_orchestration.py` — interface, complexity routing on the spec examples,
  plan validation (cycles, unknown dependencies, limits, approval reasons), lifecycle,
  parallelism and scoped inputs, retries, failure propagation, invalid output, timeouts,
  approve/reject, pause/resume, cancel, ownership, artifact linking, presence events,
  allow-list, secret redaction, child environment, Ruflo-unavailable fallback.
- `tests/integration/test_orchestration_mission.py` — a realistic mission with EZO's real
  tools: research output → DocumentAgent tools write a DOCX report → presentation tools build
  a PPTX from both structured outputs → QA verifies the artifacts; mission completes and links
  both artifacts.

Added with `RufloProvider`:

- a **mock MCP server** (a small Python stdio script in `tests/`) that implements the
  allow-listed tools — tests for start-up failure, timeout, invalid/oversized response,
  unexpected tool schema, refused non-allow-listed calls, redaction of everything sent;
- an **opt-in live test** (`EZO_TEST_RUFLO_COMMAND` set) against a pinned Ruflo version,
  skipped in CI.

## 11. Deployment

- Default: nothing to install. `EZO_ORCHESTRATION_PROVIDER=native`, `EZO_RUFLO_ENABLED=false`.
- Opt-in (when the provider ships): a `ruflo` Docker Compose profile with a Node image
  running the pinned Ruflo MCP server as a non-root user, an empty per-mission work volume,
  an internal-only network and no EZO secrets; EZO connects over stdio (sidecar exec) or
  HTTP on the internal network.
- Configuration (`.env`):

  ```
  EZO_ORCHESTRATION_PROVIDER=native|ruflo
  EZO_RUFLO_ENABLED=false
  EZO_RUFLO_COMMAND=npx -y ruflo@<reviewed-version> mcp start
  EZO_RUFLO_TIMEOUT_SECONDS=600
  ```

- Disabling: set `EZO_ORCHESTRATION_PROVIDER=native` (or `EZO_RUFLO_ENABLED=false`) and
  restart; missions keep working natively.

## 12. Development-time use of Ruflo

Not enabled in this repository. If the team later wants Ruflo to help develop EZO: run it
only in a throwaway worktree, never `init` it inside the EZO repository (it writes
`.claude/`, settings and hooks), do not install mods/plugins wholesale, review every hook
and permission it would add, and document exactly what was enabled.

## 13. Order of work

1. ✅ Audit (this document + OPEN_SOURCE_AUDIT § 6).
2. ✅ `OrchestrationProvider` interface, native runner, complexity routing, security
   boundary, tests.
3. After the roadmap foundations: mission tables + API (`/api/missions`), chat integration
   (EzoCore → mission when `assess().is_mission`), mission UI and approval cards.
4. `MCPClient` + `RufloProvider` + mock-server tests + opt-in live test + Docker profile.
5. DeveloperAgent missions with worktree isolation.
