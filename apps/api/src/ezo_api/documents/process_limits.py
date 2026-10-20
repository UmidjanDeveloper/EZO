"""Resource limits for EZO's fixed OCR/Office commands, never a user-code runner."""

from __future__ import annotations

import ctypes
import errno
import math
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from ezo_api.documents.isolation import require_isolation

NATIVE_PROCESS_LOCK = threading.Lock()
MAX_ADDRESS_SPACE = 4 * 1024 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 64 * 1024


class NativeOutputLimit(Exception):
    """A fixed native command exceeded a capture or regular-file budget."""


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    # Also clean descendants after a successful leader exits. A child keeping a pipe
    # open must never extend the deadline or survive a completed native operation.
    if os.name == "posix":
        import signal

        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def run_native(
    args: list[str],
    *,
    timeout: float,
    file_limit: int,
    stdout_limit: int,
    stderr_limit: int = MAX_DIAGNOSTIC_BYTES,
    input: bytes | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run only server-selected OCR/Office commands, with bounded parent memory.

    Anonymous temporary regular files avoid communicate()/capture_output buffering
    attacker-influenced output into API RAM. The Linux launcher enforces RLIMIT_FSIZE
    on each file; polling enforces the smaller diagnostic budgets. Input also uses a
    file, so a child refusing stdin cannot block the caller on a pipe write.
    Queue wait and execution share one wall-clock deadline. These are containment
    controls, not a filesystem sandbox or a user-code execution interface.
    """
    require_isolation()
    deadline = time.monotonic() + timeout
    if not NATIVE_PROCESS_LOCK.acquire(timeout=max(0, timeout)):
        raise subprocess.TimeoutExpired(args, timeout)
    try:
        with (
            tempfile.TemporaryFile() as stdin,
            tempfile.TemporaryFile() as stdout,
            tempfile.TemporaryFile() as stderr,
        ):
            if input:
                stdin.write(input)
            stdin.seek(0)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            process = subprocess.Popen(  # noqa: S603 - fixed server-selected native command
                limited_command(args, remaining, file_limit),
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                env=env,
                start_new_session=os.name == "posix",
            )
            try:
                while True:
                    if (
                        os.fstat(stdout.fileno()).st_size >= stdout_limit
                        or os.fstat(stderr.fileno()).st_size >= stderr_limit
                    ):
                        raise NativeOutputLimit
                    returncode = process.poll()
                    if returncode is not None:
                        if (
                            os.fstat(stdout.fileno()).st_size >= file_limit
                            or os.fstat(stderr.fileno()).st_size >= file_limit
                        ):
                            raise NativeOutputLimit
                        if os.name == "posix":
                            import signal

                            if returncode == -signal.SIGXFSZ:
                                raise NativeOutputLimit
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(args, timeout)
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=min(remaining, 0.05))
            finally:
                _kill_group(process)
            # A descendant may have written between leader exit and group cleanup.
            if os.fstat(stdout.fileno()).st_size >= min(stdout_limit, file_limit) or os.fstat(
                stderr.fileno()
            ).st_size >= min(stderr_limit, file_limit):
                raise NativeOutputLimit
            stdout.seek(0)
            stderr.seek(0)
            out, err = stdout.read(stdout_limit + 1), stderr.read(stderr_limit + 1)
            if len(out) > stdout_limit or len(err) > stderr_limit:
                raise NativeOutputLimit
            return subprocess.CompletedProcess(args, returncode, out, err)
    finally:
        NATIVE_PROCESS_LOCK.release()


def deny_network() -> None:
    """Allow local IPC, deny new IPv4/IPv6 sockets in these native child processes."""

    class Comparison(ctypes.Structure):
        _fields_ = [
            ("arg", ctypes.c_uint),
            ("op", ctypes.c_int),
            ("data_a", ctypes.c_uint64),
            ("data_b", ctypes.c_uint64),
        ]

    lib = ctypes.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Comparison),
    ]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW; load also sets no_new_privs
    if not context:
        raise OSError("Native process network filter could not be initialized")
    try:
        syscall = lib.seccomp_syscall_resolve_name(b"socket")
        for family in (socket.AF_INET, socket.AF_INET6):
            comparison = Comparison(0, 4, family, 0)  # SCMP_CMP_EQ, socket domain
            result = lib.seccomp_rule_add_array(
                context, 0x00050000 | errno.EACCES, syscall, 1, ctypes.byref(comparison)
            )
            if result < 0:
                raise OSError("Native process network policy could not be configured")
        if lib.seccomp_load(context) < 0:
            raise OSError("Native process network policy could not be enforced")
    finally:
        lib.seccomp_release(context)


def limited_command(args: list[str], timeout: float, output_bytes: int) -> list[str]:
    # Windows development retains the existing time/size limits; production is Linux.
    if sys.platform != "linux":
        return args
    return [
        sys.executable,
        "-m",
        "ezo_api.documents.process_limits",
        str(max(1, math.ceil(timeout))),
        str(output_bytes),
        *args,
    ]


def main() -> None:
    import resource

    seconds, file_bytes, binary, *args = sys.argv[1:]
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE))
    resource.setrlimit(resource.RLIMIT_CPU, (int(seconds), int(seconds) + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (int(file_bytes), int(file_bytes)))
    deny_network()
    # Python ignores these signals; exec preserves SIG_IGN unless explicitly reset.
    import signal

    for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), signal.SIG_DFL)
    os.execv(binary, [binary, *args])  # noqa: S606 - fixed binary from server configuration


if __name__ == "__main__":
    main()
