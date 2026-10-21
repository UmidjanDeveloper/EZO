# Isolated per-document executor — independent review boundary

Current Student integration review: [STUDENT_V1_REVIEW.md](STUDENT_V1_REVIEW.md).
The milestone evidence below is historical; it does not describe native worker activation.

The initial boundary was based on PR #14. Admission/recovery hardening is based
on integration `57bf803457d031c00c847aa0dd213068b5e16b96` (externally merged PR #15). It adds an **operator-only extraction boundary**, not a live native
Student worker. Production/API native execution remains disabled. No deployment,
provider call, migration, retry reset, ruleset change or automatic merge is involved.

## Trust and process ownership

`documents/executor/controller.py` accepts a trusted operator's immutable local
image ID and a bounded data-only PDF/DOCX/EPUB request. Image names, commands,
mounts and credentials cannot be supplied through the document protocol. Docker
is invoked without a shell and with `--pull=never`. The controller owns Docker
access; the API and parser never receive its socket. Running this controller on
an application host is **not** an approved deployment topology.

Every document receives a separate PID/mount/network namespace, read-only root,
128 MiB private noexec/nosuid tmpfs, 768 MiB aggregate memory limit, zero swap,
64 PID limit and one CPU quota. There are no host mounts, ports, document logs or
application/database credentials. Docker metadata is checked before input is
attached; the parser independently checks cgroup v2 controls, UID, zero effective/
bounding/ambient capabilities, no-new-privileges, read-only root and loopback-only
network. Unsupported controls fail closed.

A root `tini -> timeout` supervisor has only SETUID/SETGID/SETPCAP/KILL capabilities.
`setpriv` drops to UID/GID 10001 and removes **all** parser capabilities before
Python starts. SETPCAP is needed to drop the bounding set; it is not retained by
the parser. The unprivileged parser cannot stop the root watchdog with a signal.
The 25-second hard workload deadline survives controller SIGKILL. Supervisor exit
tears down the PID namespace, terminating detached setsid/double-fork descendants.
Controller cancellation/failure also force-removes the exact workload container.
Cleanup failure cannot be reported as success.

Input uses an anonymous temporary file. Output uses bounded pipe reads (16 MiB
JSON maximum; stderr counted/discarded after 64 KiB). Neither documents nor native
stderr are written into daemon logs or returned in error messages. Cancellation
is checked before creation, during attachment and before returning a result.
These controls are **not a complete sandbox**: containers share their host kernel;
Docker/controller compromise and kernel escapes require a dedicated, reviewed
host/VM boundary. Docker operation/cleanup deadlines can add up to 15 seconds per
control operation beyond the workload's own hard deadline.

## Extraction contract

Input is at most 5 MiB compressed/original bytes; decompressed cost is separately
bounded. Existing PDF and DOCX parsers are reused **inside** the disposable workload.
DOCX retains existing OOXML size/complexity preflight. EPUB reads at most 5,000
members/128 MiB declared expansion, 2 MiB per XML member, 2,000 manifest entries,
1,000 spine entries and 2,000,000 text characters. It rejects duplicate/encrypted/
traversing members, external references and XML DTD/entities. ZIP members are read
in memory, never extracted; scripts/styles are omitted and never executed.

Output is NFC-normalized text with original input SHA-256 and ordered global
Unicode code-point offsets. PDF pages, DOCX headings and EPUB spine member paths
provide provenance; no page number is invented for reflowable EPUB or DOCX. Empty
sections are omitted; sections are joined with exactly two newline characters.
Oversized text/section metadata is rejected rather than silently truncated.
Scanned PDFs can return `needs_ocr`; this image includes neither OCR nor Office
conversion binaries. This work does not prove LibreOffice workload compatibility.
Documents never authorize tool calls, skill installation, code execution,
repository modifications or deployment.

## Reproduce locally (test images only)

Build the normal API image from this checkout first. Its default startup still
rejects native processing. Then, from the repository root:

```sh
apps/api/.venv/bin/python scripts/test_isolated_executor.py --api-image ezo-api:ci
```

The helper builds the isolated image without adding dependencies, derives a
separate hostile-fixture image from its exact watchdog entrypoint, resolves both
to immutable IDs and runs real Docker tests. These tests require Linux Docker
with working cgroup v2 enforcement and the default seccomp restrictions. They do
not treat SQLite or a mocked subprocess as evidence of OS isolation. In this
managed cloud environment also set `BUILDX_CONFIG=/workspace/.cache/buildx`.
The existing Docker CI job executes this test path; seven required checks are
preserved. Ordinary backend suites explicitly skip these opt-in Docker cases.

Hostile fixtures cover setsid/double-fork descendants, multi-process memory
pressure with observed cgroup `oom_kill`, physical cancellation, output flooding,
and controller SIGKILL while the parser attempts to SIGSTOP the root watchdog.
Normal PDF/DOCX/EPUB extraction and fixed private-error responses are also tested.
## Atomic admission and bounded crash recovery

Controllers using this protocol share one reserved Docker name,
`ezo-native-active-v1`. Docker's atomic name reservation admits at most **one native
workload per daemon**, across processes and controller hosts, without an in-memory
semaphore or a host-local lock. A concurrent request gets `executor_busy` before
its input is attached. Docker may reserve the name before `ps/inspect` exposes
the winner; its exact reserved-name conflict is classified as busy without
treating unrelated image/authentication/daemon failures as backpressure.
This does not change database job state or retry budgets.
Callers must treat busy as backpressure, not terminal document failure.

An active, paused, restarting or freshly created reservation is never removed by
recovery. Exited/dead reservations are removed **without force**, by immutable ID;
Docker refuses the operation if the same container starts during recovery. An
unstarted create abandoned for at least 120 seconds can be reclaimed. That grace
is a reservation deadline, not a lease that authorizes late execution. Start,
inspect and cleanup always use the original immutable container ID, so a delayed
old controller cannot start or delete the replacement occupying the same name.
A random per-request label also fences cleanup when create times out before its
ID is returned. A losing creator never cleans up the winner's reservation.

Recovery inspects at most the one exact slot; it does not list/prune unrelated
containers. Required executor/slot labels must match; a foreign object at the
reserved name fails closed with `executor_slot_conflict`. Daemon errors are not
interpreted as evidence that a reservation is absent. A crashed running controller
leaves capacity occupied until the independent 25-second watchdog stops its
workload, after which the next request can reconcile it. An unstarted crash is
recoverable after the 120-second grace, without ever having attached document data.
No background service or new worker is added.

This is the conservative one-slot policy for a dedicated executor daemon. All
controllers using that daemon must run this version; mixing older UUID-named
controllers or unrelated privileged Docker clients is outside this admission
contract. It does not cap memory used by other host services or the controller's
callers. Dedicated host/VM resource monitoring remains a production gate.
A Docker daemon outage still fails closed; no global pruning or hidden fallback.

## Activation gates that remain open

- Independent review of this controller/image boundary and adversarial evidence.
- A dedicated executor host/VM, reviewed Docker/seccomp/kernel policy, aggregate
  monitoring and a reviewed deployment of this one-slot admission/recovery policy.
- An authenticated controller transport **if** it is separated from its trusted
  local operator; no unauthenticated remote Docker endpoint is acceptable.
- Durable raw-revision storage and processor-version-specific claims; binding the
  returned input SHA and exact citations to that immutable authorized revision.
- A native worker lease monitor that physically cancels this executor on
  cancellation/lease loss, plus transactionally fenced result publication. The
  existing stored-text worker's fencing remains in force; it is not repurposed.
- OCR/LibreOffice workload compatibility, required resource sizing and native
  dependency remediation. There is no new native worker in this change.

Until these gates are met, the existing safe stored-text Student workflow remains
the only enabled queue-processing path. D4/D6/D7 have measured evidence at this
operator-only boundary, **not end-to-end closure for live native jobs**.
