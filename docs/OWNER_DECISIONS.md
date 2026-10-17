# Decisions only the owner can make

These are open. AI coding sessions must **not** decide them on the owner's behalf; they only
prepare the information.

## 1. EZO's own licence — open

The repository has **no `LICENSE` file**. By default that means "all rights reserved": others
may look at the code if the repository is public, but may not copy, modify or redistribute it.

Choose deliberately, e.g.:

| Option | Meaning |
|---|---|
| No licence (current) | All rights reserved. Fine for a private product. |
| Proprietary licence text | Explicit terms for customers or partners. |
| MIT / Apache-2.0 | Anyone may reuse it, including commercially (Apache-2.0 adds a patent grant). |
| AGPL-3.0 | Others may use it, but hosted modified versions must publish their source. |

Notes:
- Third-party licences stay separate in `THIRD_PARTY_NOTICES.md`, whatever is chosen.
- The bundled Liberation Sans fonts (OFL-1.1) can be shipped with any of the options.
- The optional VoiceStudio and OpenMontage services are AGPL and run separately. They do not
  change EZO's licence as long as their code is not imported.
- If EZO will be sold or offered as a public service, ask a lawyer before choosing.

## 2. Branch protection and `main` — open

Steps are in [GIT_WORKFLOW.md](GIT_WORKFLOW.md#owner-steps-once).

## 3. Production hosting — open

Where EZO will run (own computer, VPS, cloud), which domain, and whether others will use it.
This decides authentication requirements (token mode, user accounts), backups and the
storage provider (local vs S3).

## 4. Paid providers and budgets — open

Which AI providers and models to pay for, and monthly limits. Defaults in
`apps/api/config/models.toml` are a starting point and must be kept current.

## 5. VoiceStudio default model licence — open

Its default voice model is licensed for **non-commercial use only**. Before any commercial
use, choose a different model or obtain a licence (see `docs/OPEN_SOURCE_AUDIT.md`).
