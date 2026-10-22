"""Upstream notices must travel with the package, not only repository-level docs."""

from importlib.resources import files
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name",
    [
        "RUFLO_LICENSE.txt",
        "REA_LICENSE.txt",
        "JARVIS_LICENSE.txt",
        "OPENJARVIS_LICENSE.txt",
        "LLAMAINDEX_LICENSE.txt",
    ],
)
def test_upstream_notice_is_available_as_runtime_package_data(name):
    root = Path(__file__).resolve().parents[4]
    expected = (root / "docs" / "third-party" / name).read_text()
    packaged = files("ezo_api").joinpath("_third_party", name).read_text()
    assert packaged == expected


def test_runtime_adaptation_notice_matches_attribution_source():
    root = Path(__file__).resolve().parents[4]
    expected = (root / "docs" / "third-party" / "UPSTREAM_ADAPTATIONS.md").read_text()
    assert files("ezo_api").joinpath("_third_party", "NOTICE.md").read_text() == expected
