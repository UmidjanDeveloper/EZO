# P0 GitHub protection — exact owner actions

Observed on 2026-10-19, integration c09e94ce9dc29b2e2a9ec467bbaee3c4d902d9b1.
Public GitHub /branches reports protectedByBranchProtections=false and
deleteProtected=false. The enabled Status ruleset (25371907) has include=[] and
only deletion/non_fast_forward rules, with no matching ruleset on the default branch.
This is a confirmed configuration gap, not an assumption based on missing API access.

No settings were changed. Git transport works, but api.github.com is excluded by the
managed Codex network policy. An API Forbidden response does not prove that the user's
GitHub credential lacks permission. Public pages are logged-out observations; they
cannot verify the owner's collaborator/admin capabilities or private bypass settings.

## Apply from an Android/iPhone browser

1. Open https://github.com/UmidjanDeveloper/EZO/settings/rules while signed in as owner.
   Use Chrome -> menu -> Desktop site or Safari -> Request Desktop Website if needed.
   GitHub's mobile app does not expose every ruleset setting.
2. Edit Status or create New ruleset -> New branch ruleset, name EZO P0 integration.
   Set Enforcement to Active. Include by pattern exactly:
   claude/gifted-goodall-bpf01s
   Do not select main or rename/change the default branch.
3. Enable Restrict deletions, Block force pushes, Require a pull request before merging,
   Require conversation resolution before merging, Require status checks to pass and
   Require branches to be up to date before merging.
4. Add all seven job names below. They were read directly from successful base
   [CI #86](https://github.com/UmidjanDeveloper/EZO/actions/runs/39271487039) and
   [Security #14](https://github.com/UmidjanDeveloper/EZO/actions/runs/39271487025),
   not guessed from YAML. Select the GitHub Actions integration as expected check
   source where offered. Pending/missing checks must block merge.
5. For actual independent GitHub review, require at least 1 approval, dismiss stale
   approvals on new commits and require approval of the most recent reviewable push.
   Do not lower approvals or bypass a failing check to merge this PR.
6. Keep bypass actors empty; do not add owners/admins/apps as unconditional bypasses.
   Do not enable force push/deletion exceptions, auto-merge, merge queue, deployment
   gates or unrelated organization-wide restrictions just to complete this checklist.
7. Save, then open https://github.com/UmidjanDeveloper/EZO/rules and the branch page.
   Verify a matching Active ruleset targets this exact branch. On a PR verify required
   pending/failing checks and missing independent review disable merge. Do not perform
   a destructive push/delete experiment against the integration branch.
8. The owner reviews Claude's read-only findings, the latest diff, all seven hosted
   checks for the latest SHA and residual native risks, then makes the final merge
   decision. This mission does not authorize merge or deployment.

## Exact required checks

- Secret scan (gitleaks, full history)
- API (lint, types, tests on SQLite + PostgreSQL)
- Web (lint, types, unit tests, build, e2e)
- Docker (API + web images, Compose config, API smoke test)
- Python dependencies (pip-audit)
- Node dependencies (pnpm audit)
- Container images (Trivy, fixable high and critical CVEs fail)

The Node job's development-only audit is informational within that job; inspect its
artifact as well as the production gate. Container checks report unfixed findings in
full but fail only fixable HIGH/CRITICAL. Requiring a green Security job does not
approve the remaining libxml2/native risks.

## Independent review and owner authority: important limits

A PR author cannot approve their own PR. A Claude chat/read-only review is not itself
a GitHub approval or status check. If the owner is the only eligible reviewer, the
1-approval rule will intentionally block merge until a separate trusted eligible
GitHub reviewer is arranged. Setting approvals to 0 enforces PR/checks but does NOT
satisfy an independent-review requirement; document that gap rather than claim it solved.

Review repository Settings -> Collaborators/Manage access. A collaborator with write
permission may also have merge authority. Required reviews alone do not guarantee that
only the owner can merge. Restrict non-owner permissions where the account's features
allow it; otherwise keep final owner approval as a documented release procedure and
treat exclusive technical enforcement as unverified. Do not introduce an all-rules
owner bypass to simulate merge-only authority.

For stronger owner approval enforcement, a separately approved workflow can have an
owner-controlled bot open PRs and require owner CODEOWNERS approval. That requires
review of bot identity, token scope and actual GitHub plan/rules support first; it was
not configured here. Never add a CODEOWNERS rule that claims the owner can self-approve.

Public personal repositories support basic rulesets on GitHub Free; private repository
availability depends on plan/features. If the UI is unavailable, verify owner/admin
access and current plan. Do not purchase/change plans or visibility without approval.

## Verification evidence to retain

Record ruleset URL/ID, target pattern, enforcement state, bypass actors, review policy,
the seven check names and expected source, and a safe PR screenshot showing blocked
merge while a requirement is pending. Hide tokens/private data. Record who can merge.
A green banner or Enabled label alone is not evidence that these conditions apply.
