"""End-to-end: parse_united_itinerary dispatches email input correctly."""
from __future__ import annotations

import pytest

from tests.conftest import load_yaml_case

import parse as parser


@pytest.mark.parametrize("fixture_file", [
    "test-case-email-NLY82V.yaml",
    "test-case-email-FQZ1B5.yaml",
])
def test_email_fixture_end_to_end(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(case["input_text_block"])
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
