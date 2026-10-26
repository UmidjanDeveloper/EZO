"""Summarise test results from JUnit XML files, the same way locally and in CI.

Usage:
    python scripts/test_report.py "API · SQLite=apps/api/reports/sqlite.xml" \
        "API · PostgreSQL=apps/api/reports/postgres.xml"

Prints one row per suite (collected / passed / failed / skipped) and every skip reason, so
reports never mix numbers from different environments. In GitHub Actions the same table is
appended to the job summary ($GITHUB_STEP_SUMMARY). Exits 1 if a file is missing or any test
failed. Standard library only.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Suite:
    label: str
    collected: int = 0
    failed: int = 0
    skipped: int = 0
    skip_reasons: Counter[str] = field(default_factory=Counter)
    failures: list[tuple[str, str]] = field(default_factory=list)
    """(test, first line of the failure message) so the checks API names what failed."""
    timings: list[tuple[str, str, str]] = field(default_factory=list)
    """(test, property, value) of JUnit "*_seconds*" properties (measured evidence)."""

    @property
    def passed(self) -> int:
        return self.collected - self.failed - self.skipped


def read_suite(label: str, path: Path) -> Suite:
    root = ET.parse(path).getroot()  # noqa: S314 - trusted local file
    suite = Suite(label)
    for case in root.iter("testcase"):
        suite.collected += 1
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is not None:
            suite.failed += 1
            suite.failures.append((case.get("name") or "", failure_summary(problem)))
        skipped = case.find("skipped")
        if skipped is not None:
            suite.skipped += 1
            reason = (skipped.get("message") or skipped.text or "no reason given").strip()
            suite.skip_reasons[reason.splitlines()[0][:160]] += 1
        for prop in case.iter("property"):
            name = prop.get("name") or ""
            if "_seconds" in name:
                suite.timings.append((case.get("name") or "", name, prop.get("value") or ""))
    return suite


def failure_summary(problem: ET.Element) -> str:
    """The assertion that failed, not just the test title: the first "Error"/"expect" line of
    the failure text plus the lines that say what was received, so a CI failure can be
    understood from the checks API alone."""
    lines = [line.strip() for line in (problem.text or "").splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if "Error" in line or "expect(" in line), None)
    if start is None:
        message = (problem.get("message") or "").strip().splitlines()
        return (message[0] if message else lines[0] if lines else "no message")[:400]
    detail = ("Received", "Expected", "Locator", "+ ", "- ", "Timeout", "Call log")
    keep = [lines[start]]
    keep += [line for line in lines[start + 1 : start + 12] if line.startswith(detail)][:5]
    return " | ".join(keep)[:600]


def annotations(suites: list[Suite]) -> list[str]:
    """GitHub workflow notices: readable from the checks API without downloading logs."""
    lines = [
        f"::notice title=Tests {s.label}::collected {s.collected}, passed {s.passed}, "
        f"failed {s.failed}, skipped {s.skipped}"
        for s in suites
    ]
    lines += [
        f"::error title=Failed {s.label}::{test}: {message}"
        for s in suites
        for test, message in s.failures
    ]
    lines += [
        f"::notice title=Timing {s.label}::{test} {name}={value}"
        for s in suites
        for test, name, value in s.timings
    ]
    return lines


def render(suites: list[Suite]) -> str:
    lines = [
        "| Suite | Collected | Passed | Failed | Skipped |",
        "|---|---:|---:|---:|---:|",
    ]
    for s in suites:
        lines.append(f"| {s.label} | {s.collected} | {s.passed} | {s.failed} | {s.skipped} |")
    failures = [(s.label, test, message) for s in suites for test, message in s.failures]
    if failures:
        lines += ["", "Failed tests:", ""]
        lines += [f"- {label}: {test} — {message}" for label, test, message in failures]
    reasons = [(s.label, r, n) for s in suites for r, n in s.skip_reasons.items()]
    if reasons:
        lines += ["", "Skipped tests (reason → count):", ""]
        lines += [f"- {label}: {reason} → {n}" for label, reason, n in reasons]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    suites: list[Suite] = []
    missing: list[str] = []
    for arg in argv:
        label, _, raw_path = arg.partition("=")
        path = Path(raw_path)
        if not raw_path or not path.is_file():
            missing.append(f"{label or arg}: {raw_path or '(no path)'}")
            continue
        suites.append(read_suite(label, path))
    report = render(suites)
    if missing:
        report += "\n\nMissing reports (suite did not run): " + "; ".join(missing)
    print(report)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("\n".join(annotations(suites)))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Test results\n\n" + report + "\n")
    return 1 if missing or any(s.failed for s in suites) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
