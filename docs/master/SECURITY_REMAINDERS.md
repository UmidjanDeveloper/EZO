# Security remainders — no suppression or threshold change

Local production API image (exact identity in VALIDATION.md) has44 HIGH,
zero CRITICAL and zero fixable HIGH/CRITICAL according to the current Trivy DB.
[Every HIGH package/version/ID](api-high-vulnerabilities.json) is retained.
A blank fixed version means the scanner reports no distro fix, not that a fix is
impossible forever. A green fixed-vulnerability gate does not mean the image is clean.

Relevant reachability assessment:

- util-linux family (`bsdutils`, `libblkid1`, `liblastlog2-2`, `libmount1`,
  `libsmartcols1`, `libuuid1`, `login`, `mount`, `util-linux`): four repeated
  CVEs per package are scanner package findings, not44 distinct exploit paths.
  EZO has no HTTP arbitrary mount/login/terminal tool, drops capabilities and runs
  UID10001. These lower exposure but do not prove every native library path safe.
- `libacl1`: filesystem/ACL native code remains in the image. No user-selected ACL
  operation is exposed; do not treat this as a formal unreachability proof.
- `libsystemd0`/`libudev1`: no systemd daemon or device-management endpoint is started.
  Native dependencies still exist and cannot be declared universally unreachable.
- ncurses family: no interactive terminal feature is exposed. Terminal utility and
  library code remains installed; untrusted source text is never a terminal command.
- `perl-base`: no HTTP Perl execution feature. The base distro retains this package;
  removing system packages without compatibility/packaging review is not a safe
  cosmetic fix. No scanner finding is ignored to produce green CI.

Production runtime actually reports lxml6.1.3 with compiled/runtime libxml2 2.14.6.
This does not establish that system XML/native parsers or legacy API document
rendering are a complete sandbox. Fixed data-only Student extraction is a different
boundary from hostile generated-code execution. API native OCR/Office stays disabled.

Node production dependencies report no vulnerabilities. Development dependencies
still report HIGH **GHSA-vfj7-8cjw-p6xm** (`braces3.0.3`, nested-pattern stack
exhaustion through eslint-config-next → @next/eslint-plugin-next → fast-glob →
micromatch). Advisory has no patched release (`patched_versions:<0.0.0`). No
suppression/override is added. Development/CI input is a separate exposure boundary,
not a reason to claim the advisory is irrelevant or absent.

Super Admin proposal audit records are append-only through this API, **not**
cryptographically tamper-evident against a database administrator. A hash binds
owner review to a snapshot; it does not constitute an execution capability or prove
independent review. Deployment still requires external review and owner approval.

No live cloud backup, production tenant probe, provider quality assessment, VM
escape test or4/8GB benchmark was performed. These remain explicit release gates.
