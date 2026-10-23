"""The executor child's self-check of its container boundary (fails closed)."""

from __future__ import annotations

import os
from pathlib import Path

from ezo_api.documents.executor.protocol import MEMORY_BYTES, PIDS


def verify_boundary() -> None:
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    if os.getuid() != 10001 or status["NoNewPrivs"].strip() != "1":
        raise RuntimeError("isolation_unavailable")
    if any(int(status[key].strip(), 16) for key in ("CapEff", "CapBnd", "CapAmb")):
        raise RuntimeError("isolation_unavailable")
    controls = {"memory.max": MEMORY_BYTES, "memory.swap.max": 0, "pids.max": PIDS}
    for name, expected in controls.items():
        if int(Path("/sys/fs/cgroup", name).read_text()) != expected:
            raise RuntimeError("isolation_unavailable")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    if quota == "max" or int(quota) > int(period):
        raise RuntimeError("isolation_unavailable")
    if set(os.listdir("/sys/class/net")) != {"lo"}:
        raise RuntimeError("isolation_unavailable")
    root = next(
        line.split()
        for line in Path("/proc/self/mountinfo").read_text().splitlines()
        if line.split()[4] == "/"
    )
    if "ro" not in root[5].split(","):
        raise RuntimeError("isolation_unavailable")
