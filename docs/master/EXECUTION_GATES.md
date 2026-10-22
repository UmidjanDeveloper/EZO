# K4–K8 execution and promotion gates

The current dedicated Student parser is **not** a general-purpose code sandbox.
It accepts data-only format requests and bounded extraction output. Exposing Python,
Node, shell, package managers or Ruflo's agent execution in it would break that
trust boundary. Subprocess rlimits, seccomp and Docker flags alone do not prove
VM isolation or prevent a shared-kernel escape.

## Required dedicated execution boundary

Before implementing any user/generated-code run:

1. An operator-reviewed separate VM/microVM executor host. API/DB machines expose
   no Docker socket, admin SSH or execution-control credentials to requests/models.
   Untrusted jobs cannot run alongside production data on the same privileged daemon.
2. Prebuilt immutable, verified images; pinned toolchain and SBOM. No runtime pip,
   npm, curl, install scripts or image pulls selected by source content.
3. Fresh per-job root and bounded scratch filesystem; no user home, production
   mounts, host PID namespace, cloud metadata endpoint or credential inheritance.
   Default-deny network implemented outside the guest, with no DNS/proxy escape.
4. Per-VM memory/CPU/disk/PID/output caps, hard wall deadline, one admitted job per
   executor, authoritative cancellation and orphan cleanup by the control plane.
   Never refund a consumed execution budget after a guest actually ran.
5. Durable job generation/lease fences, immutable input hash + runtime/policy digest,
   tenant-scoped result IDs, verified teardown before reusing a slot. Uncertain
   cleanup fences the executor and fails closed, not an optimistic success.
6. Hostile tests: setsid/fork bombs, SIGKILL, PID1 exit, output boundary/truncation,
   memory and CPU exhaustion, disk fill, symlink/path escapes, unexpected network,
   cancelled/lost leases, daemon restarts and wrong-user result reads. Measured
   evidence must come from the selected runtime, not a SQLite simulation.

This workspace has no /dev/kvm or approved remote executor capability. No cloud
machine was provisioned. Local containers cannot substitute for unverified hardware
or a missing independent containment review. K4 is consequently an honest blocker.

## Skill lifecycle after K4 acceptance

A proposal contains a capability goal, exact input/output schema, sources/licenses,
required permissions, policy digest and acceptance fixtures. Generated code is an
untrusted immutable artifact, not an installed tool. Static validation rejects
unknown imports, dynamic installers, runtime credentials and undeclared capability
requests; static checks are not proof of safety. Only K4 can run it for tests.

Test reports bind candidate hash, runtime digest, fixture hashes and actual outcome.
A failed/partial test never becomes a successful skill. No AI-provided score or
completion statement is accepted as execution evidence. Artifacts need signed
provenance/registry versions and immediate revocation before K6 runtime registration.

K6 may prepare an isolated branch and PR only with an owner-approved action binding
repository, base SHA, patch hash and allowed file set. Protect workflow/auth/billing
and deployment config from generated modifications. Tests and independent review
bind the exact resulting head; a changed head invalidates approvals. Merge and
deployment remain separate, explicit owner decisions. Retrieved content cannot
create or satisfy any of these approvals. No production credential enters a guest.

K8 is limited to Super Admin proposals in this candidate. Its recorded
`request_independent_review` decision is **not** permission for execution, installation,
push, merge or deployment. Do not expose an execute endpoint until K4–K6 gates pass.

## Hosting and resource acceptance

Retain the full-owner two-boundary design; do not silently co-locate the privileged
executor on the4GB primary VPS to fit a price. Before any purchase, obtain actual
inclusive primary+executor+disk+egress+offsite backup+tax quotes. If that exceeds
$10/month, report the amount and ask the owner to authorize a budget adjustment at
purchase time. None is purchased here. Run the existing benchmark protocol on real
approved4/8GB hosts; local import/build/test times are not cloud benchmark evidence.

The local VFS daemon also demonstrated a Docker-create deadline failure under
shared disk load. Idle rerun recovery is useful reliability evidence, not a cloud
capacity guarantee. Keep the15-second controller command limit and fail-closed
slot handling; benchmark image creation/cancellation latency on the actual host.
Do not silently stretch control deadlines to conceal an oversized or overloaded
executor. A future dedicated minimal parser image must preserve the same reviewed
watchdog, cgroup, UID/capability and fixed data protocol checks.
