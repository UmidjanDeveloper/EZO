"""Resource limits for EZO's fixed OCR/Office commands, never a user-code runner."""

from __future__ import annotations

import ctypes
import errno
import math
import os
import socket
import sys
import threading

NATIVE_PROCESS_LOCK = threading.Lock()
MAX_ADDRESS_SPACE = 4 * 1024 * 1024 * 1024


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
    os.execv(binary, [binary, *args])  # noqa: S606 - fixed binary from server configuration


if __name__ == "__main__":
    main()
