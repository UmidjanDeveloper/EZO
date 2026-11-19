# ruff: noqa: E501
"""Computed (never guessed) statistics for one table: column profiles, trends over a date
column, outliers, a cautious linear forecast, group totals and correlations."""

from __future__ import annotations

import itertools
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from ezo_api.analytics.table import Table, to_number, to_period

MIN_FORECAST_POINTS = 6
MAX_GROUPS = 15


@dataclass(slots=True)
class NumericProfile:
    column: str
    count: int
    missing: int
    total: float
    mean: float
    median: float
    minimum: float
    maximum: float
    stdev: float | None


@dataclass(slots=True)
class Trend:
    column: str
    points: list[tuple[date, float]]
    first: float
    last: float
    change_pct: float | None
    slope_per_step: float
    r2: float
    direction: str  # up | down | flat
    forecast: list[tuple[date, float]] = field(default_factory=list)


@dataclass(slots=True)
class Outlier:
    column: str
    row: int  # 1-based data row (header is row 1 in the file → file row = row + 1)
    value: float
    zscore: float


@dataclass(slots=True)
class Group:
    by: str
    column: str
    totals: list[tuple[str, float, int]]  # (label, sum, rows)


@dataclass(slots=True)
class Analysis:
    table: str
    rows: int
    columns: list[str]
    numeric: list[NumericProfile]
    text_columns: list[str]
    date_column: str | None
    trends: list[Trend]
    outliers: list[Outlier]
    groups: list[Group]
    correlations: list[tuple[str, str, float]]
    warnings: list[str]


def _r(value: float) -> float:
    return round(value, 4) if abs(value) < 1000 else round(value, 2)


def _fit(ys: list[float]) -> tuple[float, float, float]:
    n = len(ys)
    xs = list(range(n))
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return slope, intercept, r2


def _step(points: list[date]) -> int:
    """Typical distance between periods in days (≈30 monthly, 7 weekly, 365 yearly)."""
    gaps = sorted((b - a).days for a, b in itertools.pairwise(points) if (b - a).days > 0)
    return gaps[len(gaps) // 2] if gaps else 30


def _next(day: date, step: int) -> date:
    if 27 <= step <= 32:
        month = day.month % 12 + 1
        return date(day.year + (day.month == 12), month, 1)
    if 360 <= step <= 370:
        return date(day.year + 1, day.month, 1)
    from datetime import timedelta

    return day + timedelta(days=step)


def analyse(table: Table, horizon: int = 3) -> Analysis:
    warnings: list[str] = list(table.notes)
    if table.truncated:
        warnings.append(f"Only the first {len(table.rows)} rows were analysed.")
    cols = table.columns
    numbers: dict[str, list[float | None]] = {}
    text_cols: list[str] = []
    date_col: str | None = None
    for i, name in enumerate(cols):
        cells = [row[i] for row in table.rows]
        filled = [c for c in cells if str(c).strip()]
        if not filled:
            continue
        parsed = [to_number(c) for c in cells]
        numeric_share = sum(p is not None for p in parsed) / len(filled)
        period_share = sum(to_period(c) is not None for c in filled) / len(filled)
        if (
            date_col is None
            and period_share >= 0.8
            and not (numeric_share >= 0.8 and period_share < 1)
        ):
            date_col = name
        elif numeric_share >= 0.8:
            numbers[name] = parsed
        else:
            text_cols.append(name)

    profiles = []
    for name, values in numbers.items():
        present = [v for v in values if v is not None]
        if not present:
            continue
        profiles.append(
            NumericProfile(
                column=name,
                count=len(present),
                missing=len(values) - len(present),
                total=_r(sum(present)),
                mean=_r(statistics.fmean(present)),
                median=_r(statistics.median(present)),
                minimum=_r(min(present)),
                maximum=_r(max(present)),
                stdev=_r(statistics.stdev(present)) if len(present) > 1 else None,
            )
        )

    trends: list[Trend] = []
    if date_col is not None:
        index = cols.index(date_col)
        periods = [to_period(row[index]) for row in table.rows]
        for name, values in numbers.items():
            by_period: dict[date, float] = defaultdict(float)
            for period, value in zip(periods, values, strict=True):
                if period is not None and value is not None:
                    by_period[period] += value
            points = sorted(by_period.items())
            if len(points) < 3:
                continue
            ys = [v for _, v in points]
            slope, intercept, r2 = _fit(ys)
            first, last = ys[0], ys[-1]
            change = (last - first) / abs(first) * 100 if first else None
            spread = statistics.pstdev(ys) or 1.0
            direction = (
                "flat" if abs(slope) * len(ys) < 0.1 * spread else ("up" if slope > 0 else "down")
            )
            trend = Trend(
                column=name, points=points, first=_r(first), last=_r(last),
                change_pct=_r(change) if change is not None else None, slope_per_step=_r(slope),
                r2=round(r2, 3), direction=direction,
            )  # fmt: skip
            if len(points) >= MIN_FORECAST_POINTS and r2 >= 0.5:
                step = _step([p for p, _ in points])
                day = points[-1][0]
                for k in range(1, horizon + 1):
                    day = _next(day, step)
                    trend.forecast.append((day, _r(intercept + slope * (len(ys) - 1 + k))))
            elif len(points) >= MIN_FORECAST_POINTS:
                warnings.append(
                    f"No forecast for “{name}”: the values do not follow a straight line (R² = {r2:.2f})."
                )
            trends.append(trend)

    outliers: list[Outlier] = []
    for name, values in numbers.items():
        present = [v for v in values if v is not None]
        if len(present) < 8:
            continue
        # Robust score (median and median absolute deviation): one huge value cannot hide itself.
        median = statistics.median(present)
        mad = statistics.median(abs(v - median) for v in present)
        if not mad:
            continue
        for row, value in enumerate(values, 1):
            score = 0.6745 * (value - median) / mad if value is not None else 0.0
            if value is not None and abs(score) >= 3.5:
                outliers.append(Outlier(name, row, _r(value), round(score, 2)))

    groups: list[Group] = []
    for by in text_cols:
        index = cols.index(by)
        labels = [str(row[index]).strip() for row in table.rows]
        distinct = {label for label in labels if label}
        if not 2 <= len(distinct) <= 200 or len(distinct) > 0.8 * len(table.rows):
            continue
        for name, values in list(numbers.items())[:3]:
            sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
            for label, value in zip(labels, values, strict=True):
                if label and value is not None:
                    sums[label][0] += value
                    sums[label][1] += 1
            ranked = sorted(sums.items(), key=lambda kv: -kv[1][0])[:MAX_GROUPS]
            groups.append(Group(by, name, [(k, _r(v[0]), int(v[1])) for k, v in ranked]))
        break  # the first good category column

    correlations: list[tuple[str, str, float]] = []
    names = list(numbers)
    for a_index, a in enumerate(names):
        for b in names[a_index + 1 :]:
            pairs = [
                (x, y)
                for x, y in zip(numbers[a], numbers[b], strict=True)
                if x is not None and y is not None
            ]
            if len(pairs) < 5:
                continue
            try:
                r = statistics.correlation([x for x, _ in pairs], [y for _, y in pairs])
            except statistics.StatisticsError:
                continue
            if not math.isnan(r) and abs(r) >= 0.6:
                correlations.append((a, b, round(r, 3)))
    correlations.sort(key=lambda c: -abs(c[2]))
    return Analysis(
        table=table.name, rows=len(table.rows), columns=cols, numeric=profiles, text_columns=text_cols,
        date_column=date_col, trends=trends, outliers=outliers[:20], groups=groups,
        correlations=correlations[:5], warnings=warnings,
    )  # fmt: skip


def as_notes(a: Analysis) -> list[str]:
    """The exact numbers for the model, one fact per line."""
    lines = [f"Table “{a.table}”: {a.rows} rows, columns: {', '.join(a.columns)}."]
    for p in a.numeric:
        lines.append(
            f"“{p.column}”: {p.count} values (missing {p.missing}); sum {p.total:g}, mean {p.mean:g}, "
            f"median {p.median:g}, min {p.minimum:g}, max {p.maximum:g}"
            + (f", std {p.stdev:g}" if p.stdev is not None else "")
        )
    if a.date_column:
        lines.append(f"Time column: “{a.date_column}”.")
    for t in a.trends:
        lines.append(
            f"Trend of “{t.column}” over {len(t.points)} periods ({t.points[0][0]:%d.%m.%Y}–{t.points[-1][0]:%d.%m.%Y}): "
            f"{t.first:g} → {t.last:g}"
            + (f" ({t.change_pct:+g}%)" if t.change_pct is not None else "")
            + f", {t.direction}, change per period {t.slope_per_step:+g}, linear fit R² {t.r2:g}."
        )
        if t.forecast:
            lines.append(
                f"Linear forecast for “{t.column}” (an estimate, not a fact): "
                + "; ".join(f"{d:%m.%Y} ≈ {v:g}" for d, v in t.forecast)
            )
    for o in a.outliers:
        lines.append(
            f"Unusual value: “{o.column}” data row {o.row} = {o.value:g} (robust score {o.zscore:+g}; check it)."
        )
    for g in a.groups:
        lines.append(
            f"“{g.column}” by “{g.by}”: "
            + "; ".join(f"{label} {total:g} ({count} rows)" for label, total, count in g.totals)
        )
    for x, y, r in a.correlations:
        lines.append(f"Correlation “{x}” ~ “{y}”: r = {r:g} (association, not cause).")
    lines.extend(f"WARNING: {w}" for w in a.warnings)
    return lines
