"""Snapshot tests: existing reservation-UI output must stay byte-identical
across the refactor. If one of these fails after refactoring, the renderer
has drifted from the baseline."""
from __future__ import annotations

import pytest

from tests.conftest import load_yaml_case

# Import the parser from the PopClip bundle (added to sys.path in conftest)
import parse as parser


@pytest.mark.parametrize("fixture_file", [
    "test-case-1.yaml",
    "test-case-2.yaml",
    "test-case-3.yaml",
    "test-case-4.yaml",
    "test-case-5.yaml",
    "test-case-6.yaml",
])
def test_reservation_ui_output_matches_fixture(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(case["input_text_block"])
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
