"""Real bounded arithmetic and non-widening policy, no models or native execution."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ezo_api.orchestration.planning_policy import PlanningPolicy, availability
from ezo_api.tools.percentage import PercentageArgs, calculate_percentages


@pytest.mark.parametrize(
    ("previous", "current", "method", "expected"),
    [
        ("100", "125", "percent_change", "25.0000"),
        ("100", "125", "percent_of", "125.0000"),
        ("0.1", "0.3", "percent_change", "200.0000"),
        ("3", "1", "percent_of", "33.3333"),
        ("-100", "50", "percent_change", "-150.0000"),
        ("1", "0", "percent_of", "0.0000"),
    ],
)
def test_actual_decimal_percentages(previous, current, method, expected):
    args = PercentageArgs(
        method=method, pairs=[{"id": "x", "previous": previous, "current": current}]
    )
    result = calculate_percentages(args)
    assert result["results"][0]["result_percent"] == expected
    assert result["provenance"] == "caller_supplied_values_not_document_extraction"


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "1e9999999", "1/2", " 1", "__import__('os')", "01", 1, True]
)
def test_no_expressions_floats_or_unbounded_exponents(value):
    with pytest.raises(ValidationError):
        PercentageArgs(method="percent_of", pairs=[{"id": "x", "previous": value, "current": "1"}])


def test_ambiguous_method_and_zero_base_fail():
    with pytest.raises(ValidationError):
        PercentageArgs(pairs=[{"id": "x", "previous": "1", "current": "2"}])
    with pytest.raises(ValueError, match="nonzero"):
        calculate_percentages(
            PercentageArgs(
                method="percent_of", pairs=[{"id": "x", "previous": "-0.0", "current": "2"}]
            )
        )


def test_restriction_cannot_widen_tools_actor_or_deadline():
    actor = uuid.uuid4()
    now = datetime.now(UTC)
    policy = PlanningPolicy(actor, frozenset({"calculate_percentages"}), now + timedelta(minutes=1))
    reduced = policy.restrict(
        frozenset({"calculate_percentages", "shell_exec"}), now + timedelta(days=1)
    )
    assert reduced.tools == policy.tools and reduced.expires_at == policy.expires_at
    assert reduced.allows_plan(actor, "calculate_percentages", now)
    assert not reduced.allows_plan(uuid.uuid4(), "calculate_percentages", now)
    assert not reduced.allows_plan(actor, "shell_exec", now)
    assert not reduced.allows_plan(actor, "calculate_percentages", policy.expires_at)
    assert not policy.restrict(frozenset(), now).tools


def test_missing_controls_never_become_device_support():
    result = availability(frozenset({"paired", "native_handle"}), frozenset({"paired"}))
    assert result["available"] is False
    assert result["missing_prerequisites"] == ["native_handle"]
    assert result["execution_authorized"] is False
