import json
import subprocess
import sys

import pytest

from ezo_api.documents.process_limits import MAX_ADDRESS_SPACE, limited_command


@pytest.mark.skipif(sys.platform != "linux", reason="production Linux resource limits")
def test_native_launcher_applies_limits_before_exec() -> None:
    result = subprocess.run(  # noqa: S603 - fixed test interpreter and inline script
        limited_command(
            [
                sys.executable,
                "-c",
                "import json,resource; print(json.dumps([resource.getrlimit(k) for k in "
                "(resource.RLIMIT_CORE,resource.RLIMIT_AS,resource.RLIMIT_CPU,resource.RLIMIT_FSIZE)]))",
            ],
            2,
            123456,
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == [
        [0, 0],
        [MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE],
        [2, 3],
        [123456, 123456],
    ]


@pytest.mark.skipif(sys.platform != "linux", reason="production Linux seccomp policy")
def test_native_process_cannot_open_network_sockets_but_can_use_local_ipc() -> None:
    script = """
import socket
for family in (socket.AF_INET, socket.AF_INET6):
    try:
        socket.socket(family)
    except PermissionError:
        continue
    raise AssertionError('Native process unexpectedly opened a network socket')
with socket.socket(socket.AF_UNIX):
    pass
print('network blocked; local IPC allowed')
"""
    result = subprocess.run(  # noqa: S603 - fixed local test script; no network connection
        limited_command([sys.executable, "-c", script], 2, 123456),
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "network blocked; local IPC allowed"
