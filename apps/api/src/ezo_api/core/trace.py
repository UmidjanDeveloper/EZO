"""Safe execution tracing for agent runs.

Records step names, timings and short human-readable summaries. It never
records hidden model reasoning.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceStep:
    name: str
    status: str = "ok"
    duration_ms: int = 0
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
        }


@dataclass(slots=True)
class Tracer:
    steps: list[TraceStep] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    @contextmanager
    def step(self, name: str) -> Iterator[TraceStep]:
        record = TraceStep(name)
        begin = time.perf_counter()
        try:
            yield record
        except BaseException as exc:
            record.status = "failed"
            record.summary = record.summary or type(exc).__name__
            raise
        finally:
            record.duration_ms = int((time.perf_counter() - begin) * 1000)
            self.steps.append(record)

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def as_list(self) -> list[dict[str, Any]]:
        return [step.as_dict() for step in self.steps]
