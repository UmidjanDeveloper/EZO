"""Read-only VM evidence collection for an already approved running owner stack.

No provisioning, builds, deployments or paid/model calls. Does not itself execute
functional workloads. Run the acceptance workload separately during sampling.
Container environments are refused: cgroup probes are not VM benchmarks.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, timeout=10).strip()  # noqa: S603


def collect(containers: list[str], samples: int, interval: float) -> dict[str, object]:
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        raise RuntimeError("Container environment: a real 4/8 GB VM benchmark is unavailable.")
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    memory_kib = int(mem["MemTotal"].split()[0])
    if not 3_000_000 <= memory_kib <= 9_000_000:
        raise RuntimeError("Expected a dedicated 4 or 8 GB Linux VM.")
    evidence: dict[str, object] = {
        "scope": "VM resource sampling; workload and provider quality require separate evidence",
        "at": datetime.now(UTC).isoformat(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "memory_total_kib": memory_kib,
        "cpu_count": os.cpu_count(),
        "samples": [],
    }
    readings: list[dict[str, object]] = []
    for _ in range(samples):
        # Only IDs, state and resource limits; no Config.Env or secrets are emitted.
        states = [
            json.loads(command("docker", "inspect", "--format", "{{json .State.Running}}", name))
            for name in containers
        ]
        if not all(states):
            raise RuntimeError("A required stack component is not running.")
        stats = command("docker", "stats", "--no-stream", "--format", "{{json .}}", *containers)
        readings.append(
            {
                "at": datetime.now(UTC).isoformat(),
                "containers": [json.loads(line) for line in stats.splitlines()],
                "load": Path("/proc/loadavg").read_text().strip(),
                "memory": Path("/proc/meminfo").read_text(),
                "disk_available_bytes": os.statvfs(".").f_bavail * os.statvfs(".").f_frsize,
            }
        )
        time.sleep(interval)
    evidence["samples"] = readings
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--containers",
        nargs="+",
        required=True,
        help="All API/web/DB/consumer containers; sample executor VM separately",
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.samples <= 3600 or not 0.1 <= args.interval <= 10:
        parser.error("Bound samples to 1..3600 and interval to 0.1..10 seconds.")
    try:
        evidence = collect(args.containers, args.samples, args.interval)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        args.output.write_text(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        raise SystemExit(1) from None
    args.output.write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
