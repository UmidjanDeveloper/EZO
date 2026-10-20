"""Operator-only controller; never mount its Docker socket in API or workloads."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Literal

from ezo_api.documents.executor.protocol import (
    HARD_DEADLINE,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    MEMORY_BYTES,
    PIDS,
    ExecutorError,
    ExtractionRequest,
    ExtractionResult,
)

DOCKER = shutil.which("docker") or "/usr/bin/docker"


class IsolatedExecutor:
    """Fixed data protocol. Image IDs are trusted operator configuration."""

    def __init__(self, image: str) -> None:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise ValueError("An immutable local image ID is required")
        self.image = image

    @staticmethod
    def _docker(*args: str) -> bytes:
        try:
            completed = subprocess.run(  # noqa: S603 — fixed Docker CLI; data only on stdin
                [DOCKER, *args], capture_output=True, timeout=15, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutorError("executor_unavailable") from exc
        if completed.returncode:
            raise ExecutorError("executor_unavailable")
        return completed.stdout

    def extract(
        self,
        data: bytes,
        format: Literal["pdf", "docx", "epub"],
        *,
        cancelled: threading.Event | None = None,
    ) -> ExtractionResult:
        if len(data) > MAX_INPUT_BYTES:
            raise ExecutorError("input_limit")
        if cancelled is not None and cancelled.is_set():
            raise ExecutorError("cancelled")
        name = "ezo-native-" + uuid.uuid4().hex
        request = ExtractionRequest(format=format, data_base64=base64.b64encode(data).decode())
        process: subprocess.Popen[bytes] | None = None
        try:
            self._docker(
                "create",
                "--pull=never",
                "--name",
                name,
                "--label",
                "ezo.executor=isolated-v1",
                "--network=none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=134217728,mode=1777",  # noqa: S108 — private bounded tmpfs
                "--memory",
                str(MEMORY_BYTES),
                "--memory-swap",
                str(MEMORY_BYTES),
                "--pids-limit",
                str(PIDS),
                "--cpus=1",
                "--cap-drop=ALL",
                "--cap-add=SETUID",
                "--cap-add=SETGID",
                "--cap-add=KILL",
                "--cap-add=SETPCAP",
                "--security-opt=no-new-privileges",
                "--log-driver=none",
                "--env=HTTP_PROXY=",
                "--env=HTTPS_PROXY=",
                "--env=ALL_PROXY=",
                "--env=http_proxy=",
                "--env=https_proxy=",
                "--env=all_proxy=",
                "--interactive",
                self.image,
            )
            self._verify(name)
            # Anonymous input leaves no named private file after controller death.
            # Bounded pipe reads avoid persisting arbitrary parser output to disk.
            with tempfile.TemporaryFile() as stdin, selectors.DefaultSelector() as selector:
                stdin.write(request.model_dump_json().encode())
                stdin.seek(0)
                process = subprocess.Popen(  # noqa: S603 — generated name, no shell
                    [DOCKER, "start", "--attach", "--interactive", name],
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert process.stdout is not None and process.stderr is not None
                selector.register(process.stdout, selectors.EVENT_READ, "output")
                selector.register(process.stderr, selectors.EVENT_READ, "errors")
                output = bytearray()
                error_bytes = 0
                deadline = time.monotonic() + HARD_DEADLINE + 5
                while selector.get_map() or process.poll() is None:
                    if cancelled is not None and cancelled.is_set():
                        raise ExecutorError("cancelled")
                    if time.monotonic() >= deadline:
                        raise ExecutorError("deadline")
                    for key, _ in selector.select(timeout=0.025):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif key.data == "output":
                            if len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                                raise ExecutorError("output_limit")
                            output.extend(chunk)
                        else:
                            error_bytes += len(chunk)
                            if error_bytes > 65536:
                                raise ExecutorError("output_limit")
                    if not selector.get_map() and process.poll() is None:
                        time.sleep(0.025)
                process.wait(timeout=5)
                state = json.loads(self._docker("inspect", name))[0]["State"]
                if state["Running"] or state["ExitCode"] != 0 or process.returncode != 0:
                    raise ExecutorError("processing_failed")
                try:
                    result = ExtractionResult.model_validate_json(output)
                except ValueError as exc:
                    raise ExecutorError("invalid_result") from exc
                if result.source_sha256 != hashlib.sha256(data).hexdigest():
                    raise ExecutorError("source_mismatch")
                if cancelled is not None and cancelled.is_set():
                    raise ExecutorError("cancelled")
        finally:
            # Terminate the entire namespace, including setsid/double-fork children.
            # A daemon failure is never evidence that workload cleanup succeeded.
            try:
                self._docker("rm", "--force", name)
            except ExecutorError:
                ids = self._docker("ps", "--all", "--quiet", "--filter", "name=^/" + name + "$")
                if ids.strip():
                    raise ExecutorError("cleanup_failed") from None
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if process is not None:
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.stderr is not None:
                        process.stderr.close()

        # Cancellation can arrive while Docker performs cleanup after extraction.
        # Never acknowledge a successful result before that final check.
        if cancelled is not None and cancelled.is_set():
            raise ExecutorError("cancelled")
        return result

    def _verify(self, name: str) -> None:
        container = json.loads(self._docker("inspect", name))[0]
        host = container["HostConfig"]
        expected = {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Memory": MEMORY_BYTES,
            "MemorySwap": MEMORY_BYTES,
            "PidsLimit": PIDS,
            "NanoCpus": 1_000_000_000,
            "Privileged": False,
            "PidMode": "",
            "IpcMode": "private",
        }
        if any(host.get(key) != value for key, value in expected.items()):
            raise ExecutorError("isolation_unavailable")
        if container["Image"] != self.image or any(
            mount["Type"] != "tmpfs" or mount["Destination"] != "/tmp"  # noqa: S108 — mount validation
            for mount in container["Mounts"]
        ):
            raise ExecutorError("isolation_unavailable")
        if {cap.removeprefix("CAP_") for cap in host["CapDrop"] or []} != {"ALL"} or {
            cap.removeprefix("CAP_") for cap in host["CapAdd"] or []
        } != {
            "SETUID",
            "SETGID",
            "KILL",
            "SETPCAP",
        }:
            raise ExecutorError("isolation_unavailable")
        if "no-new-privileges" not in host["SecurityOpt"]:
            raise ExecutorError("isolation_unavailable")
