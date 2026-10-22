"""Static checks must never execute submitted source or imply runtime approval."""

import pytest

from ezo_api.learning.drafts import MAX_BYTES, validate_draft


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("", "empty_source"),
        ("x" * (MAX_BYTES + 1), "source_size_limit"),
        ("x=" + "[" * 33 + "0" + "]" * 33, "nesting_limit"),
        ("x=1\n" * 1000, "token_limit"),
        ("def broken(:", "invalid_python"),
        ("import os", "undeclared_import"),
        ("from . import thing", "undeclared_import"),
        ("from math import sqrt\nopen('/tmp/should-not-exist','w')", "restricted_name"),
        ("f = eval; f('1')", "restricted_name"),
        ("x = ().__class__", "restricted_attribute"),
    ],
)
def test_static_rejections(source, code):
    result = validate_draft(source)
    assert result["static_status"] == "rejected"
    assert code in result["findings"]
    assert result["sandbox_tested"] is False
    assert result["execution_authorized"] is False


def test_passing_static_check_is_not_execution_or_safety_proof():
    # Even an infinite loop is just data here: no hidden execution during validation.
    result = validate_draft("import math\nwhile True:\n    pass\n")
    assert result["static_status"] == "passed_static_only"
    assert result["execution_authorized"] is False
    assert result["sandbox_tested"] is False
    assert "reviewed_k4_runtime" in result["required_gates"]


def test_exact_source_hash_changes_with_whitespace():
    assert validate_draft("x=1")["source_sha256"] != validate_draft("x = 1")["source_sha256"]
