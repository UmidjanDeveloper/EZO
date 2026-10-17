# EZO architecture

This document explains how EZO is built, why, and where to extend it. It describes the code
as it exists after **Milestone 1**; later milestones add to it (see [ROADMAP.md](ROADMAP.md)).

## Overview

```
┌──────────────────────┐   HTTP + SSE    ┌──────────────────────────────────────────────┐
│ apps/web (Next.js)   │ ──────────────▶ │ apps/api (FastAPI)                           │
│ chat · projects ·    │                 │                                              │
│ memory · settings    │ ◀────────────── │  routes → EzoCore → Agent → ModelRouter      │
│ packages/ui, shared  │  streamed reply │              │          │        │           │
└──────────────────────┘                 │        MemoryService  Personality  Providers  │
                                         │              │                    │           │
                                         └──────────────┼────────────────────┼───────────┘
                                                        ▼                    ▼
                                                  PostgreSQL          Anthropic / OpenAI /
                                                  (SQLite in tests)   Gemini (or offline)
```

- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind CSS v4, Framer Motion.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy 2 (async), Alembic migrations.
- **Database:** PostgreSQL (pgvector image, ready for Milestone 2). The schema is portable,
  so tests and the no-Docker quick mode run on SQLite.
- **Monorepo:** pnpm workspace for TypeScript (`apps/web`, `packages/*`, `tests/e2e`);
  `uv` project for Python (`apps/api`).

### Mapping to the planned structure

The specification proposes `packages/agents`, `packages/tools`, `packages/memory`,
`packages/rag`, `packages/providers`. Those are Python concerns, so they live as clearly
separated sub-packages of the API instead of separate installable packages (one Python
project is much easier to install, test and debug):

| Planned | Where it lives now |
|---|---|
| `packages/agents` | `apps/api/src/ezo_api/agents/` |
| `packages/providers` | `apps/api/src/ezo_api/providers/` |
| `packages/memory` | `apps/api/src/ezo_api/memory/` |
| `packages/tools`, `packages/rag` | Milestone 2 (`ezo_api/tools/`, `ezo_api/rag/`) |
| `packages/ui` | `packages/ui/` (React components) |
| `packages/shared` | `packages/shared/` (API types + client) |
| `services/worker` | Milestone 5/8 (background sync and jobs, with Redis) |
| `knowledge/`, `infra/` | Added with the knowledge pipeline (Milestone 2) and deployment work |
| `tests/` | `tests/e2e/` (browser); unit/integration tests sit next to the API in `apps/api/tests/` |

If the Python side grows large enough, any sub-package can be extracted into its own `uv`
workspace member without changing its imports.

## Backend (`apps/api/src/ezo_api`)

```
main.py            app factory: middleware, error handlers, routers
settings.py        all configuration from environment variables / .env
services.py        builds the service container (DB, auth, router, core…)
api/routes/        HTTP endpoints: chat, conversations, memory, projects, system
core/              EzoCore pipeline, language detection, intent classification, tracing
agents/            Agent interface, catalog (availability per milestone), GeneralAgent
providers/         ModelProvider interface, adapters, router with fallback, offline mode
memory/            extraction + importance scoring, sensitivity filter, retrieval
personality/       personality profile (TOML) and system-prompt composition
auth/              AuthBackend abstraction, single-owner implementation
security/          rate limiter, audit log
db/                SQLAlchemy models, async session, portable column types
schemas/           Pydantic request/response models (mirrored in packages/shared)
```

### EzoCore: one turn

`core/ezo_core.py` turns a user message into a reply in two phases. `prepare` runs before the
HTTP response starts, so bad input becomes a normal 4xx error; `execute` streams.

| Step | What happens | Where |
|---|---|---|
| detect_language | uz / en / ru (Uzbek Latin & Cyrillic aware), or the user’s fixed preference | `core/language.py` |
| classify_intent | transparent multilingual rules with weights; records matched signals | `core/intent.py` |
| select_agent | intent → agent; unavailable agents are covered by GeneralAgent | `agents/registry.py` |
| *(persist)* | user message + an `AgentRun` (status `running`) are committed | |
| load_context | recent messages within a character budget | |
| retrieve_memory | profile (+ current project) memories ranked by relevance, importance, recency | `memory/service.py` |
| plan | agent chooses route (chat/reasoning/coding…), context mode and instructions | `agents/general.py` |
| compose_prompt | personality + rules + mode + language + memories + date | `personality/prompt.py` |
| route_model / generate | stream from the first working candidate; fall back before the first token | `providers/router.py` |
| verify | empty reply, refusal and truncation handling | |
| save_memory | capture meaningful, non-sensitive statements from the user message | `memory/extraction.py` |
| *(persist)* | assistant message, run status, provider, model, tokens, latency, steps | |

Streaming uses Server-Sent Events with four event types: `meta` (conversation, routing),
`delta` (text), `done` (saved message + run summary) and `error` (code, message, hint).
`POST /api/chat` offers the same pipeline without streaming.

### Agents

`agents/catalog.py` lists every planned agent with its milestone, preferred route, context
mode and a **limitation note**. In Milestone 1 only `GeneralAgent` is implemented. When the
intent asks for an unavailable agent (e.g. presentations), `GeneralAgent` handles the turn and
its prompt contains that agent’s limitation note, so it does not pretend to export files,
browse the web or cite laws it cannot verify. Agent selection is invisible in the UI (visible
only in the debug trace).

Adding an agent: subclass `Agent` (`agents/base.py`), implement `plan()`, mark it
`available=True` in the catalog and register it in `AgentRegistry`.

### Model providers and routing

- `providers/base.py` — `ModelProvider` interface: `stream_chat()` (required), `chat()`, and
  capability methods (`embed()` …) that raise `CapabilityNotAvailableError` until implemented.
- Adapters use the official SDKs: `anthropic_provider.py`, `openai_provider.py`,
  `gemini_provider.py`. All map vendor errors to `ProviderError` kinds
  (`auth`, `rate_limit`, `model_not_found`, `unavailable`, `timeout`, …).
- `providers/router.py` — `ModelRouter` reads `config/models.toml`. Each *route* (chat,
  reasoning, coding, long_context, vision) has ordered candidates. Only providers with a key
  are used; `EZO_PREFERRED_PROVIDER` moves one provider first. `RoutedStream` tries the next
  candidate when a provider fails **before** producing text; a failure mid-answer is reported,
  not silently retried (the user would see two different answers glued together).
- `providers/offline.py` — used only when no key is configured. It is not an AI model; it
  explains, in the user's language, how to connect one.

For Claude Opus/Sonnet-class models the Anthropic adapter enables the API’s server-side
refusal fallback. No `temperature` is sent (several current models reject it).

Adding a provider: implement `ModelProvider.stream_chat`, register it in
`providers/registry.py`, add its key to `settings.py` / `.env.example`, and list it in
`models.toml`.

### Memory

Three layers:

1. **Conversation memory** — the message history itself (`messages` table).
2. **Profile memory** — stable facts and preferences (`memory_type = profile`).
3. **Project memory** — decisions and facts of one project (`memory_type = project`).

Capture (`memory/extraction.py`): a sentence becomes a candidate only if it matches a
meaningful pattern — explicit (“eslab qol…”, “remember that…”, “запомни…”), preference,
personal fact, goal, learning difficulty, decision — each with an importance and confidence
score. Questions are ignored. `memory/sensitive.py` blocks passwords, API keys, card numbers
(Luhn-checked), passport numbers and bank accounts from automatic storage. Repeating a
statement reinforces the existing memory instead of duplicating it.

Retrieval (`memory/scoring.py`): `0.6 × relevance + 0.25 × importance + 0.15 × recency`
(30-day half-life). Relevance is lexical with prefix stemming (works reasonably for Uzbek and
Russian suffixes); Milestone 2 replaces it with embeddings through a `VectorStore` interface.
Very important profile memories are always included.

Users see, add and delete memories on the **Memory** page (and per project). Automatic memory
can be switched off in Settings.

### Personality

`config/personality.toml` holds identity, traits, rules (no sycophancy, disagree politely,
separate facts from opinions, never invent sources/laws, say when information may be
outdated), humor levels and context modes (casual, professional, technical, teacher). It
changes *how* EZO speaks, never *what* is true. The prompt is assembled stable-parts-first so
provider prompt caching stays effective.

### Data model

All primary keys are UUIDs. Migrations live in `apps/api/migrations` (Alembic).

| Table | Purpose |
|---|---|
| `users` | owner account and preferences (UI language, reply language, humor, auto-memory) |
| `projects` | user projects |
| `conversations` | chat threads (optionally in a project) |
| `messages` | user and assistant messages with metadata (provider, model, route…) |
| `memories` | profile/project memories with importance, confidence, source, sensitivity, last access; `embedding` column reserved for Milestone 2 |
| `agent_runs` | one trace per turn: intent, agent, route, provider, model, latency, tokens, steps, provider attempts, errors |
| `audit_logs` | deletions, memory changes, project creation, preference changes |

`Artifact`, `Task`, `ToolCall`, `KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk`,
`DocumentRevision`, `LanguageSession` and `LanguageMetric` arrive with the milestones that use
them, each with its own migration.

### Security

- Secrets only from environment variables; `.env` is git-ignored.
- `AuthBackend` abstraction; `LocalOwnerAuth` supports `local` (single owner, no login) and
  `token` (Bearer token, constant-time comparison) modes.
- Sliding-window rate limiting per client (chat and general buckets).
- Input validation with Pydantic; message length limit; ownership checks on every resource.
- SQLAlchemy ORM only (parameterized queries).
- Security headers on every response (pure ASGI middleware, safe for streaming).
- Audit log for important operations.
- Markdown from models is rendered without raw HTML; links open with `noopener`.
- No shell or filesystem tools exist yet; when they arrive (Milestone 6) they will require
  explicit permission and run sandboxed.

### Observability

Every turn writes an `AgentRun` with step names, durations and short summaries, provider
attempts (with error kinds), the selected provider/model, token usage and latency. The web
app’s **Iz (debug)** panel shows it. Hidden model reasoning is never stored.
`EZO_DEBUG_TRACES=false` disables the trace endpoints.

## Frontend (`apps/web`)

```
app/                  routes: / (chat), /chat/[id], /projects, /projects/[id], /memory,
                      /settings, /ezo-config (runtime config)
components/robot/     EzoRobot — animated SVG robot (idle, listening, thinking, speaking)
components/chat/      ChatView (type/talk switch), useChatSession (conversation + streaming),
                      VoiceStage (hands-free voice loop), Composer, MessageBubble, TracePanel
components/layout/    AppShell + HistoryPanel (conversation history is the only navigation)
components/pages/     Projects, Memory, Settings
lib/                  API client, speech (Web Speech API), i18n (uz/en/ru), theme, app state
```

- **Design principle:** the user only sees EZO (the robot) and the conversation history.
  Agents are chosen by EzoCore behind the scenes; nothing in the UI asks the user to pick one.
- **Voice loop** (`VoiceStage`): listen (browser speech recognition, uz-UZ / en-US / ru-RU) →
  send with `channel: "voice"` → stream the reply → read it aloud (speech synthesis, Markdown
  stripped) → listen again. Tapping the robot interrupts. With `channel: "voice"` EzoCore adds
  a prompt section asking for short, spoken-style answers; the channel is stored on the
  message. Typed and spoken turns share one conversation.
- The API client (`packages/shared`) parses the SSE stream incrementally and supports
  cancelling generation.
- `/ezo-config` serves the API URL from the `EZO_API_URL` environment variable at runtime, so
  the same build works in Docker, tests and development.
- Design tokens are CSS variables (`app/globals.css`) for light and dark themes; the palette
  takes Samarkand turquoise and lapis as accents.
- All interface text is in `lib/i18n/messages.ts`; TypeScript and a unit test ensure every
  language has every key.

## Testing

| Level | Tool | Location |
|---|---|---|
| Unit (Python) | pytest | `apps/api/tests/unit` — language, intent, memory, router, adapters (fake SDK clients), personality, rate limit |
| Integration (Python) | pytest + httpx ASGI | `apps/api/tests/integration` — full API with fake providers, real migrations, SQLite or PostgreSQL |
| Unit (TypeScript) | Vitest | `packages/shared` (SSE parser, client), `apps/web` (i18n) |
| End-to-end | Playwright | `tests/e2e` — real browser, real API (offline mode, fresh SQLite) |

## Key decisions

- **Explicit pipeline instead of an agent framework.** EzoCore is a small, readable state
  machine with traced steps. LangGraph can be introduced for multi-agent workflows
  (Milestone 8) if the explicit approach stops being enough.
- **Rule-based intent and language detection in Milestone 1.** Deterministic, free, fast,
  testable and debuggable (matched signals are recorded). The interfaces allow model-based
  classifiers later.
- **Official SDKs for providers.** Less custom HTTP code to maintain; adapters stay thin.
- **No fake features.** Anything not implemented is labelled with the milestone that adds it,
  both in the UI and in the model’s instructions.
