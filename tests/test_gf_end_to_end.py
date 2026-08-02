"""End-to-end: parse_united_itinerary against the Google Flights fixtures."""
from __future__ import annotations

from datetime import date

import pytest

from tests.conftest import load_yaml_case

import parse as parser

# Pinned so year inference is deterministic. The inferred year genuinely
# shifts with the wall clock -- e.g. "Wed, Aug 26" resolves to 2026 if run
# today but 2037 if run in 2027 -- so pinning keeps the fixtures
# deterministic and makes the intended year explicit, even though the
# renderer never prints the year, so the rendered text happens to be
# stable either way.
REF = date(2026, 8, 2)


@pytest.mark.parametrize("fixture_file", [
    "test-case-gf-1.yaml",
    "test-case-gf-2.yaml",
    "test-case-gf-3.yaml",
    "test-case-gf-4.yaml",
    "test-case-gf-5.yaml",
    "test-case-gf-rt.yaml",
])
def test_google_flights_fixture_end_to_end(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(
        case["input_text_block"], reference_date=REF)
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
