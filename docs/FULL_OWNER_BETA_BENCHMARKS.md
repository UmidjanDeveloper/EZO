# Full-owner 4/8 GB benchmark protocol and evidence boundary

**Not run on real VMs.** Managed environment reports no cloud identities or VM
capabilities. Current Linux environment has a 32 GiB cgroup memory ceiling / four-CPU
quota, not either requested VM. The read-only collector correctly refused it. No
paid VM, trial or billing was provisioned. The previous 512 MiB Office component
smoke is historical, not a complete-stack 4/8 GB benchmark.

`python scripts/benchmark_owner_stack.py --containers API WEB DB TEXT_WORKER
--samples 300 --interval 1 --output evidence.json` samples an already approved VM.
It never deploys, mutates cloud configuration, generates credentials, starts model
calls or functional workloads. It refuses wrong memory sizes/container markers;
record provider VM specification/hypervisor separately, since MemTotal alone is not
proof of a particular paid VM. Sample the separate executor VM too. Outputs contain
resource metrics, not environment/secret dumps. A sampling pass is not acceptance.

## Reproducible run after separate authorization

For **both 4 GB and 8 GB** primary Linux x86_64 VMs, record exact EZO SHA, OCI image
IDs, kernel, vCPU type/count, physical/disk class, region, price/tax, cgroup version,
PG/vector versions, filesystem size/free space and every service's effective limits.
Use identical review fixtures and pinned images. Do not compare shared CPU instances
without reporting noise. Build elsewhere; include daemon/OS/cache consumption and
disk requirements of images/logs/DB/WAL/backups. Do not enable swap for the native
parser or turn off containment to fit memory.

Run one API process, one stored-text consumer and one native slot on a **different
host**. There is no “complete one-VM stack” result under the current dedicated-host
policy. Exercise a private test dataset, not real owner documents:

1. Five-minute idle warmup/sample, then small authenticated projects/goals/manual
   memory and consent/export/delete; wrong token and foreign-owner negatives.
2. Text chat Gemini and OpenAI separately; failover before first token and interruption
   after partial output; embeddings/semantic indexing and actual citation slice
   checks. Live quality/quota calls require separately authorized AI budget and keys.
3. Student text/PDF/DOCX/EPUB fixtures below bounds; scanned PDF explicitly unavailable;
   cancel, queued contention, malformed XML/ZIP, deadline, OOM, controller crash and
   restart/lease fencing via existing hostile executor tests.
4. IELTS Parts1–3 practice, null scores without assessment; explicit voice STT/TTS,
   actual language accuracy, permission/retention and voice rights. Do not call a
   word-count heuristic pronunciation or AI assessment.
5. Office DOCX/CSV/XLSX and Presentation PPTX/HTML/SVG plus approved cloud image path;
   authenticate actual downloads and inspect rendered results. Native Office PDF
   and OCR remain blocked pending missing safe worker protocol, not silently skipped.
6. Repeat a 30-minute mixed single-owner workload and controlled overlap. Record
   p50/p95/end-to-end latency, error counts, per-service and host peak memory, CPU
   throttling, OOM/events, queue depth, successful completed documents/minute, bytes
   uploaded/exported, disk/WAL growth and real provider usage separately.
7. Stop/restart API and workers, then verify persisted DB/file hashes, bounded cleanup
   and exact citations. Perform matched DB+artifact backup/restore to approved test
   destination; record recovery time and lost-write window.

Acceptance: no security/test regression, no OOM or silent truncation/data loss,
no unbounded concurrency, no native/API cohosting, all declared working features
actually complete. Reserve at least 20% host RAM and disk after worst-case workload.
Latency expectations need measured owner acceptance; no invented SLA or arbitrary
“benchmark passed” claim. Document every unavailable feature explicitly. Both
capacity and billing/isolation gates must pass before the $10 plan is approved.
