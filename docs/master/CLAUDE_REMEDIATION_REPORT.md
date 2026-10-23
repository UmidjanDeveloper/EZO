# EZO OS — remediation report (Claude, 2026-10-23)

- **Branch and PR:** `claude/master-audit-remediation`, PR #28. The base is `main` at `38c752c`.
- **Findings:** each `F#` below refers to [CLAUDE_MASTER_AUDIT.md](CLAUDE_MASTER_AUDIT.md).
- **Diff size:** 28 code and doc files changed, +718 / −1212 lines, plus these reports. Most of the
  deletions are fake UI and prototype paths.
- **Review status:** the author of the fixes also wrote this report. **This is not an independent
  review.**

## Commits

| Commit | Fixes | Files | Regression evidence |
|---|---|---|---|
| `7397eff` ci | F6 | `.github/ci/native-packages.txt`, `scripts/ci/install-native-deps.sh`, `.github/workflows/ci.yml` | Hosted CI #203 (push) and #204 (PR) green. The install step now takes about 30 s on a cache hit. No test was skipped: a missing tool still fails the job. |
| `33a82a9` student | F7, F8, F15 | `components/student/StudentPage.tsx`, `lib/student-api.ts` (+ test) | vitest: the new 204 test. tsc and eslint clean. Playwright `student.spec.ts` passes. |
| `311c10e` jarvis | F1, F2, F3 | `components/pages/JarvisPage.tsx`, rewritten on the 4 real routes | tsc and eslint clean. No route outside `/api/jarvis/{capabilities,percentages}` is called. |
| `83e6a1d` extension | F5 | `apps/chrome-extension/*`: `content.js` and `background.js` deleted; permissions are now `["storage"]` | `apps/web/lib/chrome-extension.test.ts` asserts: no content scripts, no host permissions, and only `/api/jarvis/capabilities` called, with Authorization. |
| `d7abbfc` presentations | F9 | `api/routes/presentations.py` | `test_generated_deck_keeps_the_intake_layouts` **fails on the old code and passes on the new.** |
| `95dbd35` contracts | F10–F14 | `improvements.py`, `AdminPage.tsx`, `MemoryPage.tsx`, `PresentationsPage.tsx`, `IeltsPage.tsx` | `test_improvement_proposals.py` extended with goal, status, decision and `execution_authorized`. |
| `301fd43` docs | F4 + over-claims | `ROADMAP.md` (Phase 15, OCR limitation, Phase 3 note), `ACCEPTANCE_MATRIX.md` link, `THIRD_PARTY_NOTICES.md` | Documentation only. |
| `99c9044` orchestration | F16 | `orchestration/security.py` | `test_child_env_never_passes_node_code_loading_options` |
| `3cf2318` free beta | F17 | `free_beta.py`, `HistoryPanel.tsx`, `MemoryPage.tsx` | Free-beta and personal API tests (27 passed). Playwright `free-beta` and `memory-projects` 4/4 locally. |

## Local verification (this container)

- Web: `pnpm typecheck` and `pnpm lint` clean. vitest **61/61**. `pnpm build:web` OK.
- Playwright: **43/43** after the Student, JARVIS and contract commits. The `free-beta` and
  `memory-projects` specs re-ran after `3cf2318`: 4/4.
- API: `ruff check` clean. The targeted suites above pass. The full suite at the audit base
  `38c752c`: 1186 passed and 68 skipped on SQLite; 1201 passed on PostgreSQL.

## Hosted CI and Security

| Commit | CI | Security |
|---|---|---|
| `7397eff` | [#203 push](https://github.com/UmidjanDeveloper/EZO/actions) success, #204 PR success | not recorded here |
| `95dbd35` | #205 / #206: see the PR #28 checks | [#131/#132](https://github.com/UmidjanDeveloper/EZO/actions) success |
| `99c9044` | [#207 push](https://github.com/UmidjanDeveloper/EZO/actions/runs/39941004710), [#208 PR](https://github.com/UmidjanDeveloper/EZO/actions/runs/39941012132): see the PR #28 checks | [#133](https://github.com/UmidjanDeveloper/EZO/actions/runs/39941004697), [#134](https://github.com/UmidjanDeveloper/EZO/actions/runs/39941012135) success |

The final head's status is reported in the PR #28 description and the owner report. Only
GitHub-confirmed results count as green.

## Deliberately not changed (with reason)

- **F18, consent and recall.** This is an owner product decision (D-07). If recall is gated, memories
  the user saved explicitly stop being used.
- **F19, chat Office/OCR in production.** It needs the reviewed separate executor host. The legacy
  native path must not be re-enabled as a fallback.
- **F20–F23** are low-severity hardening items. They are listed in the audit with concrete fixes.
- **F24, the legacy launcher.** Remove it once the isolated executor is accepted.
- **F25, IELTS cue card.** Fixing it needs an API schema change; leave it for the owning team.
- **F26, i18n on 3 pages.** This is Antigravity UX work.
- **F27, VoiceStudio compose.**
  - The image digest cannot be fetched here: the registry is blocked.
  - Making the key required (`:?`) would break `docker compose config` in CI and every non-voice
    `docker compose up`.

## Never reintroduced

- The prototype Telegram, contacts, pairing token and fixture seeding.
- The JARVIS mock device.
- The global content script.
- Unrestricted Ruflo or OpenJarvis execution.
- Any copied AGPL VoiceStudio code.

## Required next step

The fixes need an independent review (Codex or a human) of PR #28 before merge. Merge is the owner's
decision.
