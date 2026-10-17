# Git workflow

## Current state (2026-10-17)

- GitHub has **one branch**, `claude/gifted-goodall-bpf01s`. All work so far is on it, and CI
  runs on every push.
- There is **no `main` branch and no branch protection yet**. Both need the repository owner:
  AI coding sessions may only push to their assigned branch and cannot change repository
  settings.

## Target workflow

```
main (protected, always green, deployable)
  ▲  pull request + CI green + review
feature branches: feat/…, fix/…, docs/…, ci/…, claude/… (AI sessions)
```

- `main` only changes through pull requests. Nobody force-pushes it.
- One feature branch per task; small, logical commits (`feat(language): …`,
  `fix(api): …`, `docs: …`, `ci: …`, `security: …`).
- A pull request merges only when:
  - **CI** passes: API lint/types/tests (SQLite and PostgreSQL)/migrations, web
    lint/types/unit/build/e2e, and the Docker images;
  - the **Security** workflow is green whenever dependencies changed;
  - someone has reviewed the diff (for AI-made PRs: the owner).
- Merge method: **squash** for small branches, **merge commit** for long-lived ones (keeps
  history).
- Releases: tag `main` (`v0.x.y`) when a roadmap phase is done.

## Owner steps (once)

1. **Create `main` from the current work** (after reviewing it):
   GitHub → *Code* → branch menu → type `main` → *Create branch: main from
   'claude/gifted-goodall-bpf01s'*.
   Or locally: `git push origin claude/gifted-goodall-bpf01s:main`.
2. **Make `main` the default branch:** *Settings → General → Default branch → main*.
3. **Protect `main`:** *Settings → Rules → Rulesets → New branch ruleset*:
   - Target: `main`
   - ✅ Restrict deletions
   - ✅ Block force pushes
   - ✅ Require a pull request before merging (1 approval if a second person reviews;
     otherwise 0, but still via PR)
   - ✅ Require status checks to pass: select
     `API (lint, types, tests on SQLite + PostgreSQL)`,
     `Web (lint, types, unit tests, build, e2e)` and
     `Docker (API + web images, Compose config, API smoke test)`
   - ✅ Require branches to be up to date before merging
4. **Open a pull request** from `claude/gifted-goodall-bpf01s` into `main` for the current
   work, or simply keep developing on new branches from `main`.
5. Optional: *Settings → Code security* → enable Dependabot alerts and secret scanning.

## Rules for AI coding sessions

- Work only on the assigned branch; never push to `main` directly.
- Never force-push shared work; never rewrite published history.
- Run the full checks before pushing (see
  [IMPLEMENTATION_STATUS.md → Verification convention](../IMPLEMENTATION_STATUS.md#verification-convention)).
- Never report a test count that CI did not produce; local-only checks are reported
  separately.
- Do not open a pull request unless the owner asks for one.
