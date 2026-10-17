# Open-source audit

> Audit date: 2026-10-17. Each repository was shallow-cloned and its `LICENSE`,
> notices, package metadata and model-licence documents were read.
> This is an engineering record, **not legal advice**. If EZO is ever sold or
> offered as a public service, have a lawyer confirm these conclusions.

## Summary

| Project | Licence | Code copied into EZO? | How EZO uses it |
|---|---|---|---|
| [APEX-UI](https://github.com/RubenM1990/APEX-UI) | MIT | **No** | Design inspiration only. EZO's orb is written from scratch. |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0-only (+ separate model licences) | **No** | Optional external service, called over its HTTP API. |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | **No** | Optional external worker (Phase 4). Pipeline ideas studied. |
| [REA](https://github.com/morluto/rea) | MIT (+ many third-party engine licences) | **No** | Not integrated. Optional future DeveloperAgent tool, off by default. |
| [open-higgsfield](https://github.com/wide-trace/open-higgsfield) | **None** (no LICENSE file) | **No** (not allowed) | Design/architecture reference only. |
| [Ruflo](https://github.com/ruvnet/ruflo) | MIT (+ Apache-2.0 fork inside, some unlabelled packages) | **No** | Optional external MCP orchestrator, **off by default**, behind a strict allow-list. Not active yet. |

**Result:** no third-party source code from these six projects is in the EZO
repository. `THIRD_PARTY_NOTICES.md` therefore lists only EZO's own package
dependencies.

---

## 1. APEX-UI

- **Repository:** https://github.com/RubenM1990/APEX-UI (commit `a8732fa`, 2026-09-11)
- **Licence:** MIT (`LICENSE`, `package.json` `"license": "MIT"`)
- **Copyright:** © 2026 Ruben Mouradian (Reznikov Engineering)
- **Commercial use:** allowed.
- **Modification:** allowed.
- **Redistribution:** allowed. The copyright and permission notice must be kept
  in copies or substantial portions.
- **Attribution:** required only if code is copied (keep the MIT notice).
- **Copyleft:** none.
- **Bundled third-party parts:** `CREDITS.md` says the WebGL shader background and the
  "overview lamp" panel are MIT components from 21st.dev. Their original authors are
  **not identified** (the credits file has placeholder links), so their attribution
  cannot be reproduced exactly. That is one more reason not to copy them.
- **Dependencies:** `three`, `@react-three/fiber`, `@react-three/postprocessing`,
  `lucide-react`, all MIT.
- **Models:** none.
- **Decision: inspiration only, no code copied.** EZO already has its own robot
  identity and uses framer-motion. Taking APEX's three.js particle core would add
  heavy WebGL dependencies to the main screen, and its shader has unclear authorship.
  EZO's `EzoPresence`/`EzoOrb` is an original SVG + framer-motion implementation. The
  ideas taken are generic: a state-driven ring, a waveform while speaking, a calm
  breathing idle state, and a status line. No APEX branding, colours (gold), names or
  layout were reused.

## 2. VoiceStudio

- **Repository:** https://github.com/debpalash/VoiceStudio (commit `481cf4c`, 2026-10-17)
- **Licence:** GNU **AGPL-3.0-only** (`LICENSE`, `LICENSE-NOTICE.md`, `pyproject.toml`)
- **Copyright:** © 2024-present Palash Debnath and VoiceStudio contributors
  (maintained by Yupcha Softwares Private Limited; contributions under a CLA).
- **Commercial use:** allowed under AGPL terms. A paid commercial licence exists for
  closed-source embedding.
- **Modification:** allowed. Any **modified** VoiceStudio offered to users over a
  network must offer them its full source under AGPL-3.0.
- **Redistribution:** allowed under AGPL-3.0, with source.
- **Attribution:** keep the licence and notices when redistributing VoiceStudio.
- **Copyleft implications:** strong network copyleft. Copying VoiceStudio code into
  EZO, or linking it into EZO's process, would put EZO under AGPL-3.0.
- **Model licences (important):**
  - `omnivoice/` Python package (TTS model code): Apache-2.0.
  - Default model `k2-fsa/OmniVoice`: code is Apache-2.0, but the **pretrained weights
    are CC-BY-NC (non-commercial)**.
  - Its `audio_tokenizer` carries separate Boson Higgs Audio 2 and Meta Llama
    community terms.
  - VoiceStudio's own `backend/config/model_licenses.json` states that **no commercial
    clearance is asserted** for any model.
  - So even where VoiceStudio's code may be used commercially, the default voice
    model may only be used **non-commercially**.
- **Interfaces available:** OpenAI-compatible HTTP API on port 3900
  (`POST /v1/audio/speech`, `POST /v1/audio/transcriptions`, `GET /v1/audio/voices`,
  `GET /v1/models`), plus a WebSocket TTS route and an MCP server. It is loopback-only
  and unauthenticated by default. The `OMNIVOICE_API_KEY` env var protects
  non-loopback access.
- **Decision: optional, separately run service, never copied or imported.** EZO gets a
  `VoiceStudioProvider` that calls VoiceStudio's HTTP API. EZO stays under its own
  licence because the two programs only exchange audio and text over a network
  protocol (an "aggregate", not a combined work). Rules:
  - Do not copy VoiceStudio source into this repository.
  - Do not vendor its Docker image or models into EZO's image.
  - Run it as its own container behind Docker's internal network, with
    `OMNIVOICE_API_KEY` set.
  - The owner is told that the default OmniVoice weights are **non-commercial**.
  - Browser speech and OpenAI voice remain available, so EZO never depends on
    VoiceStudio.
  - If EZO ever ships a **modified** VoiceStudio, that fork must be published under
    AGPL-3.0.

## 3. OpenMontage

- **Repository:** https://github.com/calesthio/OpenMontage (commit `c806645`, 2026-10-16)
- **Licence:** GNU **AGPL-3.0** (`LICENSE`, README "License: GNU AGPLv3")
- **Copyright:** OpenMontage contributors. The licence file holds the standard FSF
  text; no separate copyright line was found.
- **Commercial use:** allowed under AGPL terms.
- **Modification / redistribution:** allowed, with full source under AGPL-3.0. The
  network clause applies.
- **Copyleft implications:** same as VoiceStudio. Copying its code into EZO would make
  EZO AGPL.
- **Bundled engine: Remotion.** `remotion-composer/` depends on `remotion` and
  `@remotion/*` 4.x.
  - **Remotion is not OSI open source.** Under its own Remotion License it is free for
    individuals, non-profits and for-profit organisations with up to 3 employees.
  - Larger companies need a paid Remotion Company License.
  - Check the current terms at https://remotion.dev/license before commercial use.
- **Other models/providers:** Piper TTS (each voice model has its own licence), and
  paid APIs (Veo, Kling via fal.ai, ElevenLabs, …) under their own terms of service.
  Generated media is subject to each provider's output terms.
- **Architecture (studied):**
  - "Agent-first": an agent reads YAML pipeline manifests (`pipeline_defs/*.yaml`)
    and stage-director skills, then calls Python tools. It checkpoints after each
    stage, self-reviews (quality gates) and renders with Remotion, HyperFrames or
    FFmpeg.
  - There is **no HTTP server**. It is driven by an agent or CLI.
- **Decision: optional external worker (Phase 4), no code copied.**
  - EZO defines its own `MediaProductionProvider` interface and `StoryProject` model,
    written from scratch.
  - An `OpenMontageProvider` would hand a job brief to a separately installed
    OpenMontage in its own container (`studio` Docker profile), then collect the
    rendered file as an EZO Artifact.
  - Generic ideas reused, re-expressed in EZO's own design: staged pipeline
    (brief → script → storyboard → assets → render → review), checkpoints and quality
    gates.

## 4. REA (Reverse Engineer Anything)

- **Repository:** https://github.com/morluto/rea (commit `bd3210e`, 2026-10-17)
- **Licence:** MIT for REA-authored code (`LICENSE`, `package.json`)
- **Copyright:** © 2026 morluto
- **Commercial use / modification / redistribution:** allowed. Keep the MIT notice.
- **Third-party material:** extensive (`THIRD_PARTY_NOTICES.md`, `licenses/`):
  - Ghidra (Apache-2.0 + NOTICE), JADX (Apache-2.0), Frida (LGPL-2.0 with WxWindows
    exception).
  - MinGW-w64 runtime (GPLv3 with GCC Runtime Library Exception), BSD-3 website assets
    and others.
  - Engines are "bring your own". REA notes several upstream notice gaps.
- **Usage restrictions (`DISCLAIMER.md`):** only lawful, authorised analysis. No DRM,
  licence-check or anti-cheat circumvention, no unauthorised access, and no copying
  of proprietary code.
- **Decision: not integrated now.**
  - It is planned as an optional DeveloperAgent capability behind a
    `BinaryAnalysisProvider` interface, **disabled by default**.
  - It must only ever run on software the user owns or is authorised to analyse,
    with an explicit confirmation step.
  - Do not bundle it in the default installation.
  - Re-audit its third-party engine licences at integration time.

## 5. open-higgsfield (OpenHiggsfield)

- **Repository:** https://github.com/wide-trace/open-higgsfield (commit `b16a0ef`, 2026-09-17)
- **Licence:** **none.** There is no `LICENSE` file, `package.json` has no licence
  field (`"private": true`), and the README states no licence. Calling itself
  "open-source" in the README does not grant any rights.
- **Legal status:** all rights reserved by the author. Viewing the code is permitted,
  but copying, modifying or redistributing it is **not** permitted.
- **Trademark note:** "Higgsfield" is another company's product name. EZO must not
  use it in its UI or branding.
- **Decision: design and architecture reference only.** No code, CSS, assets or text
  are copied. Ideas studied, to be implemented in EZO's own design:
  - one prompt composer for image and video
  - a model/provider picker driven by a capability catalogue
  - generation settings
  - persistent job history
  - a media gallery

## 6. Ruflo

> Audited 2026-10-17 by reading files only: nothing was executed, installed or initialised.
> The repository's `CLAUDE.md` / `AGENTS.md` / `SKILL.md` contain instructions aimed at AI
> agents ("MUST initialize the swarm…"); they were treated as data and not followed.

- **Repository:** https://github.com/ruvnet/ruflo (commit `961ab6c8795a…`, 2026-10-17,
  *fix(cli): honor the no-update startup opt-out*). Packages `ruflo` / `@claude-flow/cli`
  3.56.10 (formerly *claude-flow*).
- **Licence:** MIT (`LICENSE`), **Copyright (c) 2024-2026 ruvnet**. Every first-party
  package that declares a licence declares MIT. Two Rust crates are "MIT OR Apache-2.0".
- **Unlabelled packages:** `@claude-flow/mcp`, `memory`, `security`, `shared`, `swarm`,
  `testing`, `deployment`, `integration`, `performance`, the `guidance-kernel` crate and
  `ruflo/src/mcp-bridge` have no licence field. The root MIT licence most likely covers them,
  but that is **not confirmed per package**.
- **Embedded third-party code:** `ruflo/src/ruvocal/` is a fork of Hugging Face chat-ui,
  Apache-2.0 (© 2018- The Hugging Face team).
- **Dependencies of note:** no AGPL/GPL/SSPL/BUSL in manifests or lockfiles. Optional
  transitive dependencies include `@anthropic-ai/claude-agent-sdk` (Anthropic's own terms)
  and LGPL-3.0 `sharp-libvips` binaries. MPL-2.0, BlueOak and Python-2.0 packages are also
  present.
- **Commercial use / modification / redistribution:** allowed (MIT). If code were copied, the
  MIT notice must be kept (and Apache-2.0 notices for any `ruvocal` part).
- **Copied into EZO:** **nothing.** EZO's `orchestration/` package is original code;
  only tool *names* are referenced, for the allow-list.

**What it is.** A CLI plus an MCP server (`npx ruflo mcp start`; stdio by default, optional
HTTP/WebSocket) for Claude Code and other coding agents. It has about 380 registered MCP
tools (the README says 314) and 46 Claude Code plugins.

**Security findings** (each checked in source; the two most serious were re-verified):

| Area | Finding | Risk for EZO |
|---|---|---|
| Shell | `terminal_execute` runs `execSync(command)` with the full `process.env`, with no gate in the main MCP server (`mcp-tools/terminal-tools.ts`). History is stored unredacted in `.claude-flow/terminals/store.json`. The codex loop uses `spawn(…, {shell:true})`. | **Critical** if reachable → hard deny-list |
| Auto-approval | `init` writes `allow: ["mcp__claude-flow__*", "Bash(npx claude-flow*)", …]`. `plugin/hooks/hooks.json` has a `PermissionRequest` hook that auto-allows every `mcp__claude-flow__*` tool (verified). | **High** → never run `init`, never install its plugin |
| Other powerful tools | `github_pr_manage` (merge), `github_workflow` (trigger), `http_fetch` (private-IP block can be lifted by env), `browser_eval`, `hooks_codemod`, `memory_import_claude` (reads `~/.claude/projects/*/memory`), `managed_agent_create` (unrestricted networking option), IPFS downloads, `config_*`, `system_reset` | **High** → deny-list |
| Model calls | `swarm_*` / `agent_spawn` only record state. `agent_execute` calls `api.anthropic.com` (or `ANTHROPIC_BASE_URL`), OpenRouter or Ollama itself, with keys from its environment. | Bypasses EZO routing/cost → only via an EZO model proxy with a mission-scoped token |
| Secrets | Reads ~180 environment variables, including all major provider keys. Passes the full environment to the child processes it starts. `providers configure --key` stores keys in plain text. Redaction only in the hooks command recorder. | **High** → minimal env, no real keys, isolated HOME |
| Self-update | Every CLI command checks npm (24 h) and **auto-installs patch releases**. Opt-outs: `CLAUDE_FLOW_AUTO_UPDATE=false`, `--no-update`, `CI=true`. Hook fallback runs `npx --yes ruflo@latest`. | Supply chain → pinned version, opt-outs set |
| Network | Promo feed `funnel.ruv.io/v1/messages` fetched without consent at session start (`RUFLO_FUNNEL=0` stops it). Telemetry is consent-gated and off by default. IPFS registries, federation relays, remote MCP servers in some plugins. | Medium → internal-only network, opt-outs |
| Files written | `init`: `.claude/` (settings, hooks, helpers, skills), `.claude-flow/`, `.swarm/memory.db`, `CLAUDE.md`, `.mcp.json`. It also appends to `~/.claude/CLAUDE.md` and refreshes `~/.claude/helpers` on every command (`RUFLO_HELPERS_LOCKED=1` stops it). | Medium → per-mission HOME and work dir |
| Background | A detached daemon is auto-started by CLI commands (`RUFLO_DAEMON_AUTOSTART=0`). Headless `claude --print` workers bypass the nested-session check; they are off by default. | Medium → opt-outs |
| HTTP MCP | No token required on loopback binds. | Medium → stdio only |
| Plugins / mods | Plugins come from an IPFS registry and are **not sandboxed** ("full process access"). Default mod trust is `observe` (blocks nothing). | High → no plugins |
| Guardrails | MCP policy gate, audit log and prompt-injection guardrail exist but are **opt-in** (`RUFLO_MCP_ENFORCE_POLICY=1`, `RUFLO_MCP_AUDIT_LOG_PATH`, `CLAUDE_FLOW_STRICT_GUARDRAIL=true`). | Enabled as a second fence |
| Useful parts | Workflows with pause/resume/cancel, missions with an authorization request, task tracking, worktree awareness, observability logs. | Value mainly for DeveloperAgent missions |

**MCP integration strategy:**
- Run as a separate process or container, launched by EZO with an argument list (no
  shell), on stdio.
- Pinned version, environment from `ruflo_env()` (minimal, hardened, isolated HOME, no
  secrets).
- EZO's allow-list plus deny-list (`orchestration/security.py`), with Ruflo's own policy gate
  on as well.
- Model calls only through an EZO proxy.
- Falls back to the native provider on any failure.

Details: [`docs/RUFLO_INTEGRATION_PLAN.md`](RUFLO_INTEGRATION_PLAN.md).

**Decision:** **approved as an optional, isolated MCP integration, not now.** No code is
copied and nothing is installed in the EZO repository or the development environment. EZO
ships the `OrchestrationProvider` interface and its own native runner, which cover mission
coordination without Ruflo. A `RufloProvider` is built after the DeveloperAgent phase, where
Ruflo's parallel coding workers and worktree support add real value. The security rules above
are preconditions. **Development-time use:** not enabled. Ruflo was not initialised or
installed in this repository, and no mods or plugins were enabled.

---

## Rules going forward

1. Re-run this audit before copying **any** external code. Record the commit hash
   inspected.
2. AGPL/GPL projects are integrated as separate processes over HTTP, WebSocket, CLI or
   MCP only. Never import them into EZO's process.
3. If code is ever copied from an MIT/Apache project:
   - add its notice to `THIRD_PARTY_NOTICES.md` in the same commit;
   - keep a header comment in the file naming the source and licence.
4. Model weights carry their own licences. Show the owner a model's licence (and
   whether it is non-commercial) before enabling it.
5. Generated media is subject to each provider's terms. EZO stores the provider and
   model with every artifact so this can be checked later.
