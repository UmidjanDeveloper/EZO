"""Running one approved skill in a locked, throw-away container.

Only the skill worker uses this (it is the only process with the Docker socket; the API never
has it). Each run is a fresh container from the pinned EZO image:

    --network none --read-only --tmpfs /tmp (16 MB, noexec) --memory 256m (no swap)
    --pids-limit 32 --cpus 1 --cap-drop ALL --security-opt no-new-privileges
    --user 10001:10001, killed after `TIMEOUT_SECONDS`

The code and its input go in on stdin, the answer comes back on stdout (capped). Inside, the
skill gets only the Python standard library; there is nothing to reach and nothing to keep.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Any

DOCKER = shutil.which("docker") or "/usr/bin/docker"
TIMEOUT_SECONDS = 20
MAX_OUTPUT_BYTES = 1_000_000
MAX_INPUT_BYTES = 200_000

# Runs inside the container: no site packages, no environment, isolated mode.
RUNNER = r"""
import json, sys, io, contextlib
request = json.loads(sys.stdin.read())
namespace = {"__name__": "ezo_skill"}
captured = io.StringIO()
try:
    with contextlib.redirect_stdout(captured):
        exec(compile(request["code"], "<skill>", "exec"), namespace)
        run = namespace.get("run")
        if not callable(run):
            raise ValueError("the skill has no run(data) function")
        result = run(request["input"])
    json.dumps(result)
    out = {"ok": True, "result": result, "printed": captured.getvalue()[-2000:]}
except Exception as exc:
    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str))
"""


class SandboxError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SandboxResult:
    ok: bool
    result: Any
    error: str | None
    duration_ms: int


def docker_args(image: str, name: str) -> list[str]:
    return [
        "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",  # noqa: S108 - the container's own tmpfs
        "--memory", "256m", "--memory-swap", "256m",
        "--pids-limit", "32", "--cpus", "1",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--user", "10001:10001", "--workdir", "/tmp",  # noqa: S108
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint", "/opt/venv/bin/python",
        image, "-I", "-S", "-c", RUNNER,
    ]  # fmt: skip


class SkillSandbox:
    def __init__(self, image: str) -> None:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise ValueError("An immutable local image ID is required")
        self.image = image

    def run(self, code: str, data: Any) -> SandboxResult:
        payload = json.dumps({"code": code, "input": data}, ensure_ascii=False).encode()
        if len(payload) > MAX_INPUT_BYTES + len(code.encode()):
            raise SandboxError("input_limit", "The input is too large.")
        name = f"ezo-skill-{uuid.uuid4().hex[:12]}"
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 — fixed Docker CLI; code and data on stdin
                [DOCKER, *docker_args(self.image, name)],
                input=payload,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            subprocess.run([DOCKER, "kill", name], capture_output=True, timeout=10, check=False)  # noqa: S603
            raise SandboxError(
                "timeout", f"The skill ran longer than {TIMEOUT_SECONDS} s."
            ) from None
        except OSError as exc:
            raise SandboxError(
                "sandbox_unavailable", "Docker is not available to the skill worker."
            ) from exc
        duration = round((time.monotonic() - started) * 1000)
        if len(completed.stdout) > MAX_OUTPUT_BYTES:
            raise SandboxError("output_limit", "The skill's answer is too large.")
        try:
            answer = json.loads(completed.stdout.decode("utf-8") or "{}")
        except ValueError:
            reason = (
                "out of memory" if completed.returncode == 137 else f"exit {completed.returncode}"
            )
            raise SandboxError(
                "crashed", f"The skill stopped without an answer ({reason})."
            ) from None
        if not isinstance(answer, dict) or "ok" not in answer:
            raise SandboxError("crashed", "The skill stopped without an answer.")
        return SandboxResult(
            ok=bool(answer["ok"]),
            result=answer.get("result"),
            error=None if answer["ok"] else str(answer.get("error") or "error")[:500],
            duration_ms=duration,
        )
