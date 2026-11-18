"""How a district project is going, computed only from stored numbers (no model).

For each person: plan, done, percent, and the share expected by today when the project has
start and end dates (a straight line from start to deadline). A person is *behind* when they
have done less than 80% of what was expected by today, or nothing at all after the first
three days; a project without dates uses 50% of plan as the line once anything is reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

BEHIND_SHARE = 0.8
GRACE_DAYS = 3


@dataclass(frozen=True, slots=True)
class PersonStatus:
    member_id: str
    name: str
    area: str
    target: float
    done: float
    expected: float | None
    behind: bool

    @property
    def percent(self) -> float | None:
        return round(100 * self.done / self.target, 1) if self.target > 0 else None


@dataclass(slots=True)
class ProjectStatus:
    name: str
    unit: str
    target: float
    done: float
    expected_share: float | None
    """Share of the plan expected by today (0–1), None without dates."""
    days_left: int | None
    people: list[PersonStatus] = field(default_factory=list)

    @property
    def percent(self) -> float | None:
        return round(100 * self.done / self.target, 1) if self.target > 0 else None

    @property
    def behind(self) -> list[PersonStatus]:
        return sorted(
            (p for p in self.people if p.behind),
            key=lambda p: (p.percent if p.percent is not None else 0.0, p.name),
        )


def expected_share(start: date | None, deadline: date | None, today: date) -> float | None:
    if start is None or deadline is None or deadline <= start:
        return None
    elapsed = (today - start).days
    return max(0.0, min(1.0, elapsed / (deadline - start).days))


def compute(
    *,
    name: str,
    unit: str,
    start: date | None,
    deadline: date | None,
    today: date,
    rows: list[tuple[str, str, str, float, float]],
) -> ProjectStatus:
    """`rows`: (member_id, name, area, target, done) per assignment."""
    share = expected_share(start, deadline, today)
    started_days = (today - start).days if start else None
    people: list[PersonStatus] = []
    for member_id, person, area, target, done in rows:
        if share is not None:
            expected = target * share
            late_start = done <= 0 and started_days is not None and started_days >= GRACE_DAYS
            behind = target > 0 and (late_start or done < BEHIND_SHARE * expected)
        else:
            expected = None
            behind = target > 0 and done < 0.5 * target and any(r[4] > 0 for r in rows)
        people.append(PersonStatus(member_id, person, area, target, done, expected, behind))
    return ProjectStatus(
        name=name,
        unit=unit,
        target=sum(p.target for p in people),
        done=sum(p.done for p in people),
        expected_share=share,
        days_left=(deadline - today).days if deadline else None,
        people=people,
    )


def _n(value: float) -> str:
    return f"{value:g}"


def describe(status: ProjectStatus, limit: int = 15) -> str:
    """Facts for the model (and the page): totals, pace and who is behind."""
    lines = [
        f"Project «{status.name}»: done {_n(status.done)} of {_n(status.target)} {status.unit}"
        + (f" ({status.percent:g}%)." if status.percent is not None else ".")
    ]
    if status.expected_share is not None:
        lines.append(
            f"Expected by today: {round(100 * status.expected_share):g}% of the plan"
            + (
                f"; {status.days_left} day(s) left until the deadline."
                if status.days_left is not None
                else "."
            )
        )
    lines.append(f"People: {len(status.people)}; behind: {len(status.behind)}.")
    for person in status.behind[:limit]:
        pct = f"{person.percent:g}%" if person.percent is not None else "no plan"
        expected = (
            f", expected ~{_n(round(person.expected))}" if person.expected is not None else ""
        )
        lines.append(
            f"- BEHIND: {person.name}"
            + (f" ({person.area})" if person.area else "")
            + f": {_n(person.done)} of {_n(person.target)} ({pct}{expected})"
        )
    ahead = sorted(
        (p for p in status.people if not p.behind and p.percent is not None),
        key=lambda p: -(p.percent or 0),
    )[:5]
    for person in ahead:
        done, target = _n(person.done), _n(person.target)
        lines.append(f"- on track: {person.name}: {done} of {target} ({person.percent:g}%)")
    return "\n".join(lines)
