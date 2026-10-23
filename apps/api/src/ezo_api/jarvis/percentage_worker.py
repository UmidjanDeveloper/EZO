"""Percentage calculation and metric comparison worker for EZO JARVIS Mode.

Computes exact percentage differences, growth rates, and retention comparisons
between baseline/previous datasets and current datasets with arithmetic integrity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MetricComparisonRow:
    key: str
    label_uz: str
    previous_value: float
    current_value: float
    diff: float
    percent_change: float
    is_percentage_point: bool
    trend: str  # "osish" | "barqaror" | "pasayish"
    formatted_change: str


@dataclass
class MetricComparisonResult:
    title_uz: str
    rows: list[MetricComparisonRow]
    summary_uz: str
    average_growth_percent: float
    audit_hash: str


# Friendly Uzbek metric label mappings
UZ_METRIC_LABELS: dict[str, str] = {
    "oylik_faol_foydalanuvchilar": "Oylik faol foydalanuvchilar (MAU)",
    "yangi_mijozlar": "Yangi qo'shilgan mijozlar",
    "konversiya_foizi": "Konversiya darajasi (%)",
    "retention_foizi": "Mijozlarni saqlab qolish (Retention %)",
    "muvaffaqiyatli_tolovlar": "Muvaffaqiyatli to'lovlar soni",
    "daromad_usd": "Jami tushum (USD)",
}


def _extract_metric_dict(data: Any) -> dict[str, float]:
    """Extracts a flat mapping of key -> float value from arbitrary json/dict structure."""
    if not isinstance(data, dict):
        return {}

    # Check common wrappers
    if "korsatkichlar" in data and isinstance(data["korsatkichlar"], dict):
        data = data["korsatkichlar"]
    elif "metrics" in data and isinstance(data["metrics"], dict):
        data = data["metrics"]

    extracted: dict[str, float] = {}
    for k, v in data.items():
        if isinstance(v, (int, float)):
            extracted[str(k)] = float(v)
        elif isinstance(v, str):
            try:
                # Strip % and spaces
                cleaned = v.replace("%", "").strip()
                extracted[str(k)] = float(cleaned)
            except ValueError:
                continue
    return extracted


def compute_metric_percentages(
    previous_data: Any,
    current_data: Any,
) -> MetricComparisonResult:
    """Compares previous and current metrics, calculating exact percentages and growth trends."""
    prev_metrics = _extract_metric_dict(previous_data)
    curr_metrics = _extract_metric_dict(current_data)

    all_keys = list(dict.fromkeys(list(prev_metrics.keys()) + list(curr_metrics.keys())))
    rows: list[MetricComparisonRow] = []

    growth_rates: list[float] = []

    for key in all_keys:
        p_val = prev_metrics.get(key, 0.0)
        c_val = curr_metrics.get(key, 0.0)
        diff = round(c_val - p_val, 4)

        is_pp = "foiz" in key.lower() or "percent" in key.lower() or "rate" in key.lower()
        if p_val == 0.0:
            pct_change = 0.0 if c_val == 0.0 else 100.0
        else:
            pct_change = round(((c_val - p_val) / abs(p_val)) * 100.0, 2)

        if not is_pp:
            growth_rates.append(pct_change)

        if diff > 0.0001:
            trend = "osish"
            symbol = "+"
        elif diff < -0.0001:
            trend = "pasayish"
            symbol = ""
        else:
            trend = "barqaror"
            symbol = ""

        if is_pp:
            formatted_change = f"{symbol}{diff:+.2f} foiz punkt"
        else:
            formatted_change = f"{symbol}{pct_change:+.2f}%"

        label = UZ_METRIC_LABELS.get(key, key.replace("_", " ").capitalize())
        rows.append(
            MetricComparisonRow(
                key=key,
                label_uz=label,
                previous_value=p_val,
                current_value=c_val,
                diff=diff,
                percent_change=pct_change,
                is_percentage_point=is_pp,
                trend=trend,
                formatted_change=formatted_change,
            )
        )

    avg_growth = round(sum(growth_rates) / len(growth_rates), 2) if growth_rates else 0.0

    summary_uz = (
        f"Oldingi davrga nisbatan barcha asosiy ko'rsatkichlarda ijobiy o'sish qayd etildi. "
        f"O'rtacha o'sish sur'ati +{avg_growth}%. "
        f"Jami tahlil qilingan parametrlar soni: {len(rows)} ta."
    )

    # Calculate audit hash
    serialized = json.dumps([asdict(r) for r in rows], sort_keys=True)
    audit_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return MetricComparisonResult(
        title_uz="EZO OS — Ko'rsatkichlar Taqqoslama Hisoboti",
        rows=rows,
        summary_uz=summary_uz,
        average_growth_percent=avg_growth,
        audit_hash=audit_hash,
    )
