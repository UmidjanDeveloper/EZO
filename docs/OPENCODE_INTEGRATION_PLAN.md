# OpenCode — evaluation and integration plan

**Status:** evaluation only. Nothing is installed, imported or started by EZO. This document
recommends how OpenCode *could* later serve as an **optional, isolated coding execution
backend** for EZO's DeveloperAgent (ROADMAP Phase 9). OpenCode never replaces EzoCore.

**Evaluated:** 2026-10-18. Project: <https://github.com/anomalyco/opencode> (the old
`sst/opencode` name redirects there).

## How this audit was done (and its limits)

- EZO's build environment cannot reach github.com or opencode.ai directly. The facts below
  were read through a web-fetch service from the repository's own files (`LICENSE`,
  `package.json` files, `packages/core/src/*.ts`, `specs/v2/tools.md` and the documentation
  source in `packages/web/src/content/docs/*.mdx` on the `dev` branch), npm registry
  metadata, the GitHub container registry page and the GitHub releases page.
- **The V2 documentation site (opencode.ai/v2/docs) could not be reached.** V2 facts come from
  source code and npm metadata only; anything marked *not verified* must be checked before any
  integration work starts.

## Summary

| Question | Finding |
|---|---|
| License | **MIT** (`LICENSE`, "Copyright (c) 2025 opencode"). The root, `@opencode/cli`, `@opencode/sdk` and `@opencode/plugin` packages all declare MIT. |
| Dependency licences | Spot checks: MIT and Apache-2.0 only. A **full transitive licence scan was not done**; whether any copyleft dependency exists is *not verified*. |
| Versions | **V1** (GitHub releases v1.19.x; npm `opencode-ai`, `@opencode-ai/sdk` 1.19.3) and **V2** (`dev` branch; npm `@opencode/cli`, `@opencode/sdk`, `@opencode/plugin` 2.0.32) exist side by side, with breaking changes between them. V1 and V2 cannot be installed side by side. |
| SDK / client | A JS/TS SDK only. V1: `createOpencode()` / `createOpencodeClient({ baseUrl })`, with types generated from the server's OpenAPI 3.1 spec (`/doc`). V2: `@opencode/sdk` built on Effect. No Python SDK, so EZO would use the **HTTP API**. |
| Server | `opencode serve`, default `127.0.0.1:4096`, with SSE event streams (`/event`, `/global/event`). **Unauthenticated by default**; HTTP Basic auth only when `OPENCODE_SERVER_PASSWORD` is set. `--mdns` binds 0.0.0.0. |
| Plugins | Loaded from `.opencode/plugins/`, `~/.config/opencode/plugins/` and npm packages named in config, which are **installed automatically at startup**. Plugins run **in-process with full trust** (Bun shell `$`, SDK client). A plugin tool **overrides a built-in tool of the same name**. In V2, a plugin hook can change permission decisions. |
| Workspace / worktree isolation | Working directory and git-worktree support. V2 has a worktree manager (plain child processes) and an experimental workspace driver model (`OPENCODE_EXPERIMENTAL_WORKSPACES`). **No documented OS-level or container sandbox** for tool execution; concrete container drivers are *not verified*. |
| Permissions | Per-tool `allow` / `ask` / `deny` (read, edit, glob, grep, bash by parsed command, webfetch, websearch, external_directory, task, skill, lsp …), glob patterns, last match wins. **Most defaults are `allow`** (only `.env` reads are denied; external directories and loop detection `ask`). `--auto` approves every `ask`. In V2 each tool calls the permission check itself; there is no central enforcement point. |
| Secrets | Provider keys are stored in **plaintext JSON** (`~/.local/share/opencode/auth.json`, MCP OAuth in `mcp-auth.json`). Provider env vars are read. Config supports `{env:VAR}` and `{file:path}` substitution and remote `.well-known/opencode` org config. |
| Network by default | models.dev model list, update checks, LSP downloads, npm plugin installs; V1 "share" uploads a session to opncd.ai when used. Each has an off switch (`OPENCODE_DISABLE_MODELS_FETCH`, `autoupdate: false`, `OPENCODE_DISABLE_LSP_DOWNLOAD`, `OPENCODE_DISABLE_DEFAULT_PLUGINS`, `share: "disabled"`). Telemetry is *not verified*. The purpose of the `@opentunnel/client` dependency is *not verified*. |
| Deployment | Native binaries per platform via npm optional dependencies (linux x64/arm64 incl. musl, macOS, Windows), an install script, Homebrew/scoop/choco/AUR/nix, and a Docker image `ghcr.io/anomalyco/opencode` (amd64/arm64; tags for 1.19.3 and 2.0.32). Resource needs are *not verified*. |

## Recommendation

OpenCode is a capable, permissively licensed coding agent. EZO **may** use it later, but only as
an **optional, replaceable execution backend** behind EZO's own DeveloperAgent, not as a
decision maker and not as part of normal chat. The decisive gaps for embedding are:

1. there is **no sandbox**: permissions are logical checks inside the OpenCode process;
2. the defaults are permissive (`allow`) and plugins are fully trusted;
3. secrets are kept in plaintext files, and the server is unauthenticated by default;
4. the V1 → V2 transition means API churn, and the V2 docs were unreachable.

So EZO would supply the isolation, the policy and the secrets boundary itself. Do **not**
install OpenCode in production yet.

## Target architecture (when Phase 9 starts)

```
EzoCore ── DeveloperAgent (EZO: plan, policy, approvals, review, report)
               │  CodingBackend interface (EZO code)
               ├── NativeCodingBackend (EZO's own sandboxed repo tools)   ← default
               └── OpenCodeBackend (optional, off by default)
                        │ HTTP + SSE to 127.0.0.1 inside the sandbox only
                        ▼
              ┌──────────── disposable sandbox container ────────────┐
              │ opencode serve (pinned version, password set)         │
              │ one git worktree of ONE approved repository           │
              │ no host mounts except that worktree; no Docker socket │
              │ egress: model API only (via EZO proxy), nothing else  │
              └───────────────────────────────────────────────────────┘
```

- **`CodingBackend` interface** (EZO): `start_task(repo, goal, limits)`, `events()`, `diff()`,
  `run_checks()`, `cancel()`, `close()`. The DeveloperAgent talks only to this interface, so
  OpenCode can be removed without touching EzoCore.
- **EzoCore keeps every decision**: what to change, whether a result is acceptable, and every
  approval (push, deploy, delete, dependency changes, network access).

## Hard rules for an OpenCodeBackend

| Area | Rule |
|---|---|
| Process | Runs only in a disposable container per task (non-root, read-only root filesystem, CPU/memory/time limits, no privileged mode, no Docker socket, seccomp default). Destroyed after the task. |
| Filesystem | One git worktree of one approved repository is mounted. No home directory, no host paths, no EZO storage. `external_directory: deny`. |
| Shell | `bash` defaults to **deny**, with an allow-list of exact commands EZO chooses (tests, lint, typecheck, build for that repo). Never `--auto`. Never arbitrary shell from model input. |
| Edits | Allowed only inside the worktree; EZO reviews the diff before anything leaves the sandbox. |
| Git | No credentials in the sandbox. OpenCode can never `git push`; EZO pushes after approval, from outside. |
| Network | Default deny. Only the model API endpoint, through EZO's egress proxy. `webfetch`/`websearch` deny. Set `OPENCODE_DISABLE_MODELS_FETCH`, `OPENCODE_DISABLE_LSP_DOWNLOAD`, `OPENCODE_DISABLE_DEFAULT_PLUGINS`, `autoupdate: false`, `share: "disabled"`. |
| Plugins / MCP | None, except plugins EZO vendors and pins after review. No npm auto-install at startup. No MCP servers. |
| Secrets | No EZO secrets in the sandbox. A short-lived, scoped model key per task (or a proxy that adds the key outside the sandbox), so `auth.json` never holds a real long-lived key. `.env*` reads stay denied. |
| Server | `OPENCODE_SERVER_PASSWORD` set to a random per-task value; bound to 127.0.0.1 inside the container; EZO reaches it through the container network only. |
| Config | Generated by EZO per task (permissions, agents, providers). Managed-config precedence (`/etc/opencode/…`) is used to stop the repository's own config from widening permissions. Remote `.well-known` config disabled. |
| Audit | Every OpenCode event (tool calls, permission asks, diffs) is mirrored into EZO's tool-call log; secrets are redacted (EZO's `redact_secrets`). |
| Version | Pinned (V2 only after its API is stable); a licence and changelog review before each upgrade. |

## Evaluation steps before any code

1. Read the V2 docs (opencode.ai/v2/docs) and confirm the server API, permission and plugin
   behaviour above. The facts from source code must be re-checked against them.
2. Do a full transitive licence scan of the pinned version (`npx license-checker` or an SBOM
   with `syft`) and record it in `docs/OPEN_SOURCE_AUDIT.md`.
3. Find out what `@opentunnel/client` is used for and confirm it can be turned off; confirm
   that telemetry is off.
4. Prototype in the sandbox with a throwaway repository. Prove that `deny` rules, the
   command allow-list, the network block and the absence of credentials hold even when the
   model tries to get around them (red-team prompts).
5. Only then write `OpenCodeBackend` (off by default, `EZO_CODING_BACKEND=native`).

## What this plan does not do

- It does not install, vendor or call OpenCode.
- It does not give OpenCode any EZO secret, shell, filesystem, network or Git access.
- It does not change EzoCore, the agent catalog or the current tool registry.

## Sources

- License and packages: `LICENSE`, `package.json`, `packages/{cli,sdk,plugin}/package.json` on
  `dev` (raw.githubusercontent.com/anomalyco/opencode/dev/…).
- Docs source: `packages/web/src/content/docs/{index,sdk,server,web,cli,plugins,permissions,agents,policies,config,providers,mcp-servers,troubleshooting,network}.mdx`;
  `share.mdx` at tag v1.19.3.
- Code and specs: `packages/core/src/{permission,worktree,workspace}.ts`, `specs/v2/tools.md`.
- npm: registry.npmjs.org (`@opencode/cli`, `@opencode/sdk`, `opencode-ai`, `@opencode-ai/sdk`,
  spot-checked dependencies). Container image: github.com/anomalyco/opencode/pkgs/container/opencode.
- Releases: github.com/anomalyco/opencode/releases (v1.19.0–v1.19.3).
