"""Skills: drafting, the owner's approval of exact code, queueing runs and waiting for them.

Static checks here are a courtesy for the reviewer (they catch obvious misuse early); the
security boundary is the locked container in `sandbox.py`, and the owner's approval of the
code's exact hash. A run always executes the approved hash, never newer code.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import Skill, SkillRun

MAX_CODE_BYTES = 32_000
WAIT_SECONDS = 40.0
# Modules a skill may import (pure computation and text). Everything else is refused before
# review; the container has no network or writable disk either way.
ALLOWED_IMPORTS = frozenset(
    "math statistics decimal fractions datetime calendar json re string textwrap itertools "
    "functools collections dataclasses typing random unicodedata difflib csv io operator "
    "bisect heapq enum zoneinfo".split()
)
BLOCKED_NAMES = frozenset({"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"})


class SkillError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def check_code(code: str) -> dict[str, Any]:
    """{"ok": bool, "problems": [...], "imports": [...]} — what the reviewer sees."""
    problems: list[str] = []
    imports: list[str] = []
    if len(code.encode()) > MAX_CODE_BYTES:
        problems.append(f"The code is longer than {MAX_CODE_BYTES} bytes.")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "ok": False,
            "problems": [f"Syntax error on line {exc.lineno}: {exc.msg}"],
            "imports": [],
        }
    has_run = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                root = name.split(".")[0]
                imports.append(root)
                if root not in ALLOWED_IMPORTS:
                    problems.append(
                        f"Import of “{root}” is not allowed (only pure computation modules)."
                    )
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            problems.append(f"“{node.id}” is not allowed.")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr != "__init__"
        ):
            problems.append(f"Access to “{node.attr}” is not allowed.")
        elif isinstance(node, ast.FunctionDef) and node.name == "run" and node in tree.body:
            has_run = True
    if not has_run:
        problems.append("The code must define a top-level function run(data).")
    return {"ok": not problems, "problems": sorted(set(problems)), "imports": sorted(set(imports))}


async def save_draft(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    description: str,
    input_hint: str,
    code: str,
) -> Skill:
    """A new skill, or new code for an existing one (its approval is cleared)."""
    name = " ".join(name.split())[:80] or "Ko‘nikma"
    checks = check_code(code)
    skill = await db.scalar(select(Skill).where(Skill.user_id == user_id, Skill.name == name))
    digest = sha256(code)
    if skill is None:
        skill = Skill(user_id=user_id, name=name, code=code, code_sha256=digest)
        db.add(skill)
    elif skill.code_sha256 != digest:
        skill.code, skill.code_sha256 = code, digest
        skill.approved_sha256, skill.approved_at = None, None
    skill.description = description[:2000]
    skill.input_hint = input_hint[:2000]
    skill.checks = checks
    skill.status = "approved" if skill.approved_sha256 == digest else "draft"
    await db.flush()
    return skill


async def approve(db: AsyncSession, skill: Skill, code_sha256: str) -> Skill:
    """The owner approves exactly the code they saw (its hash must match)."""
    if code_sha256 != skill.code_sha256:
        raise SkillError(
            "code_changed", "The code changed since you looked at it; review it again.", 409
        )
    if not (skill.checks or {}).get("ok"):
        raise SkillError(
            "checks_failed", "This code did not pass the checks and cannot be approved."
        )
    skill.approved_sha256, skill.approved_at, skill.status = code_sha256, utcnow(), "approved"
    await db.flush()
    return skill


async def queue_run(db: AsyncSession, skill: Skill, data: Any) -> SkillRun:
    if skill.status != "approved" or skill.approved_sha256 != skill.code_sha256:
        raise SkillError("not_approved", "This skill's current code is not approved yet.", 409)
    run = SkillRun(
        user_id=skill.user_id,
        skill_id=skill.id,
        code_sha256=skill.approved_sha256,
        input=data if isinstance(data, dict) else {"value": data},
        status="queued",
    )
    db.add(run)
    await db.flush()
    return run


async def wait_for(
    sessionmaker: Any, run_id: uuid.UUID, seconds: float = WAIT_SECONDS
) -> SkillRun | None:
    """Poll until the worker finished the run (or the time is up)."""
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        async with sessionmaker() as session:
            run: SkillRun | None = await session.get(SkillRun, run_id)
            if run is not None and run.status in ("completed", "failed"):
                return run
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(0.5)


async def find_skill(db: AsyncSession, user_id: uuid.UUID, text: str) -> Skill | None:
    """The approved skill whose name appears in the message (longest name first)."""
    skills = list(
        await db.scalars(select(Skill).where(Skill.user_id == user_id, Skill.status == "approved"))
    )
    lowered = text.lower()
    for skill in sorted(skills, key=lambda s: -len(s.name)):
        if skill.name.lower() in lowered:
            return skill
    return None
