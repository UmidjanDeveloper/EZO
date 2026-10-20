"""Repository-owned adversarial fixture; never shipped in runtime images."""

import base64
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

from ezo_api.documents.executor.child import verify_boundary

verify_boundary()
request = json.load(sys.stdin)
data = base64.b64decode(request["data_base64"])
mode = data.decode()
text = mode
if mode in ("detached", "stall", "watchdog"):
    reader, writer = os.pipe()
    if os.fork() == 0:
        os.close(reader)
        os.setsid()
        if os.fork() != 0:
            os._exit(0)
        os.write(writer, b"ready")
        while True:
            time.sleep(1)
    os.close(writer)
    assert os.read(reader, 5) == b"ready"
    os.close(reader)
    if mode == "watchdog":
        # Both timeout and tini are root; parser must not stop either watchdog.
        for pid in (1, os.getppid()):
            try:
                os.kill(pid, signal.SIGSTOP)
            except PermissionError:
                pass
            else:
                raise RuntimeError("watchdog was stoppable")
    if mode != "detached":
        while True:
            time.sleep(1)
elif mode == "flood":
    sys.stdout.write("x" * (17 * 1024 * 1024))
    sys.stdout.flush()
    time.sleep(10)
elif mode == "memory":
    children = []
    for _ in range(3):
        pid = os.fork()
        if pid == 0:
            memory = bytearray(320 * 1024 * 1024)
            time.sleep(5)
            os._exit(0)
        children.append(pid)
    for pid in children:
        os.waitpid(pid, 0)
    events = dict(
        line.split() for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines()
    )
    assert int(events["oom_kill"]) > 0
    text = "aggregate_oom_enforced"
print(
    json.dumps(
        {
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "text": text,
            "sections": [{"start": 0, "end": len(text)}],
        }
    ),
    flush=True,
)
