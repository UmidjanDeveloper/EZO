"""Run real Docker controls locally/CI; never enables an API execution path.

Usage: apps/api/.venv/bin/python scripts/test_isolated_executor.py --api-image ezo-api:ci
The API image must already be built from the current checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker") or "/usr/bin/docker"


def docker(*args: str) -> str:
    return subprocess.check_output([DOCKER, *args], text=True).strip()  # noqa: S603


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--junitxml", default="reports/isolated-executor.xml")
    options = parser.parse_args()
    base = docker("image", "inspect", options.api_image, "--format", "{{.Id}}")
    docker(
        "build",
        "--pull=false",
        "--build-arg",
        "API_IMAGE=" + options.api_image,
        "--file",
        str(REPO / "apps/api/src/ezo_api/documents/executor/Dockerfile"),
        "--tag",
        "ezo-executor:regression",
        str(REPO / "apps/api"),
    )
    if docker("image", "inspect", options.api_image, "--format", "{{.Id}}") != base:
        raise RuntimeError("API image changed during build")
    image = docker("image", "inspect", "ezo-executor:regression", "--format", "{{.Id}}")
    entrypoint = json.loads(
        docker("image", "inspect", image, "--format", "{{json .Config.Entrypoint}}")
    )
    assert entrypoint[-2:] == ["-m", "ezo_api.documents.executor.child"]
    with tempfile.TemporaryDirectory(prefix="ezo-owned-probe-") as directory:
        root = Path(directory)
        shutil.copyfile(REPO / "apps/api/tests/fixtures/executor/probe.py", root / "probe.py")
        # The probe inherits exactly the reviewed root-watchdog/UID/capability drop.
        (root / "Dockerfile").write_text(
            "FROM ezo-executor:regression\nCOPY --chmod=0444 probe.py /app/probe.py\n"
            + "ENTRYPOINT "
            + json.dumps([*entrypoint[:-2], "/app/probe.py"])
            + "\n"
        )
        docker("build", "--pull=false", "--tag", "ezo-executor:hostile-regression", str(root))
    probe = docker("image", "inspect", "ezo-executor:hostile-regression", "--format", "{{.Id}}")
    env = dict(os.environ, EZO_EXECUTOR_TEST_IMAGE=image, EZO_EXECUTOR_PROBE_IMAGE=probe)
    return subprocess.call(  # noqa: S603 — repository-owned pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rs",
            "tests/integration/test_isolated_executor_container.py",
            "tests/integration/test_student_executor.py",
            "--junitxml=" + options.junitxml,
        ],
        cwd=REPO / "apps/api",
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
