# Separate executor host — requirements

- **Status:** BLOCKED (no host, no Oracle connector).
- **Status:** REQUIRES OWNER APPROVAL.

## Two different things that must not be merged

| | Native document executor (exists in code) | K4 generated-code sandbox (does not exist) |
|---|---|---|
| **Input** | Owner-uploaded PDF, DOCX or EPUB bytes (≤5 MiB) through a **fixed data protocol** on stdin | Arbitrary AI-generated programs |
| **Code** | `ezo_api.student.worker` and `documents/executor/{controller,child,epub,protocol}.py` | None. `EXECUTION_GATES.md` keeps K4 BLOCKED. |
| **Isolation** | Per-document Docker container:<br>- `--network=none`, read-only root, 128 MiB tmpfs;<br>- 768 MiB memory, swap 0, 64 PIDs, ≤1 CPU;<br>- 25 s watchdog, `cap-drop ALL`, UID 10001;<br>- teardown of the whole container. | Needs a VM or microVM per job (Firecracker needs `/dev/kvm`), or at least gVisor, with no secrets and no network |
| **Evidence** | CI `docker` job: per-document isolation, hostile descendants, OOM, cancellation and controller-crash tests pass | None |

**Passing the parser tests is not evidence that arbitrary code can run safely.** Never let
K4 reuse this executor.

Also not covered here:
- **OCR** (Tesseract) is unsupported in the Student executor protocol; scanned PDFs return
  `ocr_required`.
- **LibreOffice conversion** is not wired into any executor protocol.
- Both stay **disabled**. Enabling them needs a new reviewed job/result protocol, not
  packages installed on the API host.

## Host requirements (native document executor)

- **Host:**
  - a dedicated Linux VM, separate from the primary host;
  - Docker with cgroup v2 (the controller verifies effective cgroups and namespace flags);
  - **one parser slot**, with concurrency 1 per daemon.
- **Resources:** at least 2 GB RAM (one 768 MiB parser + controller + daemon + OS); 4 GB is
  comfortable.
- **Image:** a pinned, locally built executor image ID (`--image sha256:...`). It must be
  built and tested for the host's architecture.
- **Command:**
  `python -m ezo_api.student.worker --worker-id owner-native-1 --image sha256:<reviewed> --ack-dedicated-executor-host`
- **Database:**
  - a restricted identity reaching the primary PostgreSQL over **WireGuard**;
  - the `pg_hba` rule allows only the tunnel address, with `hostssl` and `verify-full`;
  - raw bytes live in PostgreSQL (`student_raw_revisions`), so the executor needs **no file
    volume and no API keys**.
- **Revocation:** stop the worker and remove the WireGuard peer. Jobs then stay queued and
  fail closed.
- **Network:** the host needs outbound access only to the primary's WireGuard endpoint and
  to OS updates. Parser containers have no network.

## Oracle Always Free A1 as the executor — assessment

| Question | Answer |
|---|---|
| CPU and RAM | 2 OCPU / 12 GB after 2026-06-15 (press report). Enough for one slot. |
| ARM64 | `python:3.13-slim` and `node:22-alpine` digests are multi-arch indexes (checked earlier). pgvector publishes arm64. **Python wheels:** every compiled wheel in `uv.lock` has an aarch64 build. **The executor image has not been built or tested on arm64.** A CI `buildx` arm64 job is required first. |
| Capacity and account | **Unverified.** No connector exists. There are recurring "Out of capacity" reports, and idle reclamation applies (95th-percentile CPU, network and memory all below 20% over 7 days). |
| Isolation | Docker namespaces plus cgroups, the same as CI. gVisor (`runsc`, systrap, no KVM needed) could be added as a second layer later. |
| Hostile documents | Covered by the executor's hostile-fixture tests in CI (amd64 only). |
| Worker authentication | The database role plus WireGuard keys. No HTTP API is exposed. |
| Reliability | Free tier with no SLA, and the allowance was already cut once. Acceptable **only** because failure leaves jobs queued and nothing leaks. |

**Verdict:** a plausible $0 executor, but **unverified**.

## Steps before provisioning (none are done)

1. Owner: check the A1 quota and capacity in the Oracle console (checklist O1).
2. Add a CI job that builds the executor image for `linux/arm64` and runs
   `scripts/test_isolated_executor.py`.
3. Write the WireGuard and `pg_hba` addition for `deploy/primary`. This is a reviewed change,
   not done yet.
4. Only after an acceptance run on the real host may native Student parsing be called
   available.
