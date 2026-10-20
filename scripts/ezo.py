#!/usr/bin/env python3
"""EZO helper: one command for every common task.

    python scripts/ezo.py doctor    check that everything needed is installed
    python scripts/ezo.py setup     install dependencies and create .env
    python scripts/ezo.py dev       run EZO locally (database + API + web)
    python scripts/ezo.py test      run lint, type-checks and tests
    python scripts/ezo.py build     production builds

On Windows use `py scripts\\ezo.py ...` if `python` is not found.
Only the Python standard library is used, so this works before `setup`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- output


def _supports_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _supports_color() else text


def info(text: str) -> None:
    print(_paint("36", "› ") + text, flush=True)


def ok(text: str) -> None:
    print(_paint("32", "✓ ") + text, flush=True)


def warn(text: str) -> None:
    print(_paint("33", "! ") + text, flush=True)


def fail(text: str, hint: str | None = None) -> None:
    print(_paint("31", "✗ ") + text, flush=True)
    if hint:
        print("  " + hint, flush=True)


class StepFailedError(Exception):
    pass


# --------------------------------------------------------------------------- helpers


def tool(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    """Run a command, streaming its output. Raises StepFailedError on failure."""
    printable = " ".join(cmd)
    info(f"{printable}   (in {cwd.relative_to(ROOT) if cwd != ROOT else '.'})")
    executable = tool(cmd[0])
    if executable is None:
        raise StepFailedError(f"'{cmd[0]}' is not installed. Run: python scripts/ezo.py doctor")
    result = subprocess.run([executable, *cmd[1:]], cwd=cwd, env=env, check=False)  # noqa: S603
    if result.returncode != 0:
        raise StepFailedError(f"Command failed ({result.returncode}): {printable}")


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or read_env_file().get(
        "DATABASE_URL", "postgresql+psycopg://ezo:ezo@localhost:5432/ezo"
    )


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def database_reachable(url: str) -> bool:
    if url.startswith("sqlite"):
        return True
    parsed = urlparse(url.replace("+psycopg", ""))
    return port_open(parsed.hostname or "localhost", parsed.port or 5432)


def wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310 (local URL)
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def docker_compose() -> list[str] | None:
    docker = tool("docker")
    if docker is None:
        return None
    probe = subprocess.run(  # noqa: S603
        [docker, "compose", "version"], capture_output=True, check=False, text=True
    )
    return ["docker", "compose"] if probe.returncode == 0 else None


# --------------------------------------------------------------------------- commands


def cmd_doctor(_: argparse.Namespace) -> int:
    problems = 0
    print("EZO doctor — checking your computer\n")

    if sys.version_info >= (3, 12):  # noqa: UP036 (users may run an old Python)
        ok(f"Python {sys.version.split()[0]}")
    else:
        problems += 1
        fail(f"Python {sys.version.split()[0]} is too old", "Install Python 3.12 or newer.")

    checks = [
        ("uv", "Python package manager", "https://docs.astral.sh/uv/getting-started/installation/"),
        ("node", "Node.js 20.9+", "https://nodejs.org (LTS version)"),
        ("pnpm", "JavaScript package manager", "Run: corepack enable   (or: npm install -g pnpm)"),
    ]
    for name, label, hint in checks:
        if tool(name):
            ok(f"{label} ({name})")
        else:
            problems += 1
            fail(f"{label} ({name}) not found", hint)

    if docker_compose():
        ok("Docker with Compose (for the PostgreSQL database)")
    else:
        warn(
            "Docker not found. You need it for the database, or set "
            "DATABASE_URL=sqlite:///./ezo.db in .env for the quick no-Docker mode."
        )

    if ENV_FILE.exists():
        ok(".env file exists")
        env = read_env_file()
        keys = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY") if env.get(k)]
        if keys:
            ok("AI provider keys: " + ", ".join(keys))
        else:
            warn("No AI provider key in .env — EZO will run in offline mode.")
    else:
        warn(".env file missing. Run: python scripts/ezo.py setup")

    url = database_url()
    if database_reachable(url):
        ok("Database reachable" + (" (SQLite)" if url.startswith("sqlite") else ""))
    else:
        warn("PostgreSQL is not running. Start it with: docker compose up -d db")

    print()
    if problems:
        fail(f"{problems} problem(s) found. Fix them and run doctor again.")
        return 1
    ok("Everything needed is installed.")
    return 0


def cmd_setup(_: argparse.Namespace) -> int:
    if not ENV_FILE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        ok("Created .env from .env.example — add an AI provider key to it.")
    else:
        ok(".env already exists (left unchanged)")
    run(["uv", "sync"], cwd=API_DIR)
    run(["pnpm", "install"])
    print()
    ok("Setup finished. Next: python scripts/ezo.py dev")
    return 0


def migrate(env: dict[str, str] | None = None) -> None:
    run(["uv", "run", "alembic", "upgrade", "head"], cwd=API_DIR, env=env)


def ensure_database() -> None:
    url = database_url()
    if database_reachable(url):
        return
    compose = docker_compose()
    if compose is None:
        raise StepFailedError(
            "PostgreSQL is not running and Docker is not installed.\n"
            "  Install Docker Desktop, or put DATABASE_URL=sqlite:///./ezo.db in .env."
        )
    info("Starting the PostgreSQL database with Docker…")
    run([*compose, "up", "-d", "db"])
    parsed = urlparse(url.replace("+psycopg", ""))
    for _ in range(60):
        if port_open(parsed.hostname or "localhost", parsed.port or 5432):
            time.sleep(2)  # give PostgreSQL a moment to accept logins
            return
        time.sleep(1)
    raise StepFailedError("The database did not start. See: docker compose logs db")


def start(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    executable = tool(cmd[0])
    if executable is None:
        raise StepFailedError(f"'{cmd[0]}' is not installed. Run: python scripts/ezo.py doctor")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0  # type: ignore[attr-defined]
    return subprocess.Popen(  # noqa: S603
        [executable, *cmd[1:]],
        cwd=cwd,
        env=env,
        creationflags=flags,
        start_new_session=not IS_WINDOWS,
    )


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def cmd_dev(args: argparse.Namespace) -> int:
    if not ENV_FILE.exists():
        warn(".env not found — running setup first.")
        cmd_setup(args)
    ensure_database()
    migrate()

    if not IS_WINDOWS:
        # Treat `kill` / a closed terminal like Ctrl+C so the child processes stop too.
        signal.signal(signal.SIGTERM, _interrupt)
        signal.signal(signal.SIGHUP, _interrupt)

    api = start(
        [
            "uv",
            "run",
            "uvicorn",
            "ezo_api.main:create_app",
            "--factory",
            "--reload",
            "--port",
            "8000",
        ],
        cwd=API_DIR,
    )
    web = start(["pnpm", "--filter", "@ezo/web", "dev"], cwd=ROOT)
    processes = [api, web]
    try:
        if wait_for("http://localhost:8000/api/health", 60) and wait_for(
            "http://localhost:3000", 120
        ):
            print()
            ok(
                "EZO is running → open http://localhost:3000   (API docs: http://localhost:8000/docs)"
            )
            info("Press Ctrl+C to stop.")
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        fail("A process stopped unexpectedly. Read the messages above.")
        return 1
    except KeyboardInterrupt:
        print()
        info("Stopping EZO… (messages from the stopped processes below are normal)")
        for process in processes:
            stop(process)
        ok("EZO stopped.")
        return 0
    finally:
        for process in processes:
            stop(process)


def cmd_migrate(_: argparse.Namespace) -> int:
    ensure_database()
    migrate()
    ok("Database is up to date.")
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    """Run only the API. `--e2e` uses a fresh SQLite database and offline mode."""
    env = dict(os.environ)
    if args.e2e:
        e2e_dir = Path(tempfile.mkdtemp(prefix="ezo-e2e-"))
        db_path = e2e_dir / "e2e.db"
        env.update(
            DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
            EZO_STORAGE_DIR=str(e2e_dir / "storage"),
            ANTHROPIC_API_KEY="",
            OPENAI_API_KEY="",
            GEMINI_API_KEY="",
            TAVILY_API_KEY="",
            EZO_ENV="test",
            EZO_AUTH_MODE="local",
            EZO_RATE_LIMIT_CHAT="1000",
            EZO_RATE_LIMIT_DEFAULT="10000",
        )
    migrate(env)
    run(
        [
            "uv",
            "run",
            "uvicorn",
            "tests.e2e_app:create_fixture_app" if args.e2e else "ezo_api.main:create_app",
            "--factory",
            "--port",
            str(args.port),
        ],
        cwd=API_DIR,
        env=env,
    )
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    run(["uv", "run", "ruff", "check", "src", "tests", "migrations"], cwd=API_DIR)
    run(["uv", "run", "ruff", "format", "--check", "src", "tests", "migrations"], cwd=API_DIR)
    run(["uv", "run", "mypy"], cwd=API_DIR)
    # JUnit reports feed scripts/test_report.py: the same table as in CI (see
    # IMPLEMENTATION_STATUS.md, "Verification convention").
    reports = [f"API · SQLite={API_DIR / 'reports' / 'sqlite.xml'}"]
    sqlite_env = {k: v for k, v in os.environ.items() if k != "EZO_TEST_DATABASE_URL"}
    run(
        ["uv", "run", "pytest", "-q", "-rs", "--junitxml=reports/sqlite.xml"],
        cwd=API_DIR,
        env=sqlite_env,
    )
    if os.environ.get("EZO_TEST_DATABASE_URL"):
        run(["uv", "run", "pytest", "-q", "-rs", "--junitxml=reports/postgres.xml"], cwd=API_DIR)
        reports.append(f"API · PostgreSQL={API_DIR / 'reports' / 'postgres.xml'}")
    run(["pnpm", "lint"])
    run(["pnpm", "typecheck"])
    run(
        [
            "pnpm",
            "test",
            "--reporter=default",
            "--reporter=junit",
            "--outputFile=reports/vitest.xml",
        ]
    )
    reports += [
        f"Web unit={ROOT / 'apps' / 'web' / 'reports' / 'vitest.xml'}",
        f"Shared unit={ROOT / 'packages' / 'shared' / 'reports' / 'vitest.xml'}",
    ]
    if args.e2e:
        env = dict(os.environ, EZO_PYTHON=sys.executable)
        run(["pnpm", "test:e2e"], env=env)
        reports.append(f"Playwright e2e={ROOT / 'tests' / 'e2e' / 'reports' / 'junit.xml'}")
    print()
    run([sys.executable, str(ROOT / "scripts" / "test_report.py"), *reports])
    print()
    ok("All checks passed (local verification — CI numbers are reported separately).")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    run(["uv", "run", "python", "-m", "compileall", "-q", "src"], cwd=API_DIR)
    run(["pnpm", "build:web"])
    if args.docker:
        compose = docker_compose()
        if compose is None:
            raise StepFailedError("Docker is not installed.")
        run([*compose, "build"])
    print()
    ok("Build finished.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ezo", description="EZO helper commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check installed tools").set_defaults(func=cmd_doctor)
    sub.add_parser("setup", help="install dependencies, create .env").set_defaults(func=cmd_setup)
    sub.add_parser("dev", help="run EZO locally").set_defaults(func=cmd_dev)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(func=cmd_migrate)
    api = sub.add_parser("api", help="run only the API")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--e2e", action="store_true", help="fresh SQLite DB, offline mode")
    api.set_defaults(func=cmd_api)
    test = sub.add_parser("test", help="lint, type-check and test everything")
    test.add_argument("--e2e", action="store_true", help="also run browser end-to-end tests")
    test.set_defaults(func=cmd_test)
    build = sub.add_parser("build", help="production builds")
    build.add_argument("--docker", action="store_true", help="also build Docker images")
    build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except StepFailedError as exc:
        print()
        fail(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
