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
from datetime import UTC, datetime
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
SLOT_NAME = "ezo-native-active-v1"
CREATED_GRACE_SECONDS = 120


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
            # During concurrent create, Docker reserves a name before ps/inspect
            # necessarily exposes the container. Recognize only its exact fixed
            # name conflict; authentication, image and daemon errors stay distinct.
            conflict = f'Conflict. The container name "/{SLOT_NAME}" is already in use'.encode()
            if args and args[0] == "create" and conflict in completed.stderr:
                raise ExecutorError("executor_busy")
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
        request_id = uuid.uuid4().hex
        self._recover_slot()
        container_id: str | None = None
        request = ExtractionRequest(format=format, data_base64=base64.b64encode(data).decode())
        process: subprocess.Popen[bytes] | None = None
        try:
            try:
                created = self._docker(
                    "create",
                    "--pull=never",
                    "--name",
                    SLOT_NAME,
                    "--label",
                    "ezo.executor=isolated-v1",
                    "--label=ezo.executor.slot=single-v1",
                    "--label=ezo.executor.request=" + request_id,
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
            except ExecutorError as exc:
                # Docker name reservation is atomic across processes/hosts sharing
                # this daemon. A losing creator must never remove the winner.
                occupant = self._slot_id()
                if occupant is not None and self._owned_id(request_id) is None:
                    raise ExecutorError("executor_busy") from exc
                raise
            container_id = created.decode().strip()
            if not re.fullmatch(r"[a-f0-9]{64}", container_id):
                container_id = None
                raise ExecutorError("invalid_container_identity")
            self._verify(container_id)
            # Anonymous input leaves no named private file after controller death.
            # Bounded pipe reads avoid persisting arbitrary parser output to disk.
            with tempfile.TemporaryFile() as stdin, selectors.DefaultSelector() as selector:
                stdin.write(request.model_dump_json().encode())
                stdin.seek(0)
                process = subprocess.Popen(  # noqa: S603 — generated name, no shell
                    [DOCKER, "start", "--attach", "--interactive", container_id],
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
                state = json.loads(self._docker("inspect", container_id))[0]["State"]
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
            owned_id: str | None = None
            try:
                owned_id = container_id or self._owned_id(request_id)
                if owned_id is not None:
                    self._docker("rm", "--force", owned_id)
            except ExecutorError:
                if owned_id is None:
                    raise
                ids = self._docker("ps", "--all", "--quiet", "--filter", "id=" + owned_id)
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

    def _slot_id(self) -> str | None:
        value = (
            self._docker(
                "ps", "--all", "--quiet", "--no-trunc", "--filter", "name=^/" + SLOT_NAME + "$"
            )
            .decode()
            .strip()
        )
        if not value:
            return None
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ExecutorError("invalid_container_identity")
        return value

    def _owned_id(self, request_id: str) -> str | None:
        identity = self._slot_id()
        if identity is None:
            return None
        record = json.loads(self._docker("inspect", identity))[0]
        labels = record["Config"].get("Labels") or {}
        if labels.get("ezo.executor.request") == request_id:
            return identity
        return None

    def _recover_slot(self) -> None:
        identity = self._slot_id()
        if identity is None:
            return
        record = json.loads(self._docker("inspect", identity))[0]
        labels = record["Config"].get("Labels") or {}
        if (
            labels.get("ezo.executor") != "isolated-v1"
            or labels.get("ezo.executor.slot") != "single-v1"
        ):
            raise ExecutorError("executor_slot_conflict")
        state = record["State"]
        created = datetime.fromisoformat(record["Created"].replace("Z", "+00:00"))
        abandoned_create = (
            state["Status"] == "created"
            and (datetime.now(UTC) - created).total_seconds() >= CREATED_GRACE_SECONDS
        )
        if state["Running"] or not (state["Status"] in ("exited", "dead") or abandoned_create):
            raise ExecutorError("executor_busy")
        # No force: if another operator starts this same ID after inspection,
        # Docker refuses removal. Never kill a healthy workload during recovery.
        try:
            self._docker("rm", identity)
        except ExecutorError:
            if self._slot_id() == identity:
                raise ExecutorError("executor_busy") from None

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
