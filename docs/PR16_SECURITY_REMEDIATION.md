# PR #16: compromised CA trust remediation

Failed run: https://github.com/UmidjanDeveloper/EZO/actions/runs/39548377361
at `e6041da09d1924543dffb2ef21724644e0bb824f`.

| Scanner | Package | Installed | Fixed | Advisory |
|---|---|---|---|---|
| pip-audit 2.10.1 | certifi | 2026.7.22 | 2026.10.19 | PYSEC-2026-4320; GHSA-6q48-6c7w-9gw2 |
| Trivy 0.76.0, CRITICAL | certifi | 2026.7.22 | 2026.10.19 | GHSA-6q48-6c7w-9gw2 |

The reproduced reports provide no CVE alias; none is invented. Both failures have
the same root cause: the bundled `emSign ECC Root CA - G3` anchor can validate
certificates issued through compromised intermediate CA keys.

Original hosted JSON artifacts could not be downloaded: the managed network
rejects api.github.com with `Forbidden`, including `gh run download`. A normal
public artifact-page request also failed. The identifiers above came from new
local JSON reports using the exact vulnerable lock and the original API runtime's
dependencies, with a newly downloaded Trivy database. They reproduce one Python
vulnerability and 44 HIGH / 1 CRITICAL / 1 fixable HIGH-or-CRITICAL. They are not
represented as the original hosted artifact files.

## Fix and compatibility

- Require `certifi>=2026.10.19` and refresh only certifi in `uv.lock`, including
  published wheel/source hashes. This is a security floor for an existing
  transitive dependency, not an additional installed library.
- A package-only rebuild still trusted G3 through Python's system CA context.
  Disable exactly that root in Debian's CA configuration and rebuild the system
  store with `update-ca-certificates --fresh` in the API Dockerfile. Other roots
  remain; package/scanner databases are retained.
- Test actual trust anchors, not only a version string. The unit test checks
  certifi; the same repository-owned script runs inside the production API image
  to check both certifi and system contexts. ISRG Root X1 and unaffected emSign
  G1/C1/C3 must remain trusted. Hostname/certificate verification stays enabled.
- The existing Security image job runs this additional smoke check. Audit severity
  gates, raw reports, scanner versions and required job names are unchanged. No
  vulnerability is ignored or suppressed.

The rebuilt local API image reports 44 HIGH, 0 CRITICAL and 0 fixable HIGH/CRITICAL.
Remaining HIGH OS findings have no fixed version in that database and remain risk.
This is not a zero-vulnerability or production-ready claim.

No routes, migrations, native execution guards, queue semantics, credentials, TLS
verification flags, deployment configuration or GitHub rulesets are changed.
Exact test counts, image/head IDs and hosted PR conclusions are recorded in the
accompanying execution evidence report.
