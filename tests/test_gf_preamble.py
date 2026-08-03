"""The selected-trip view puts the total fare and the trip type in a preamble
above the first slice, which is the only place that view states a price.

Search results state the price per slice, so the preamble is consulted only
for what the slices did not supply.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)


def _read(name: str) -> str:
    return (TEST_CASES / name).read_text(encoding="utf-8")


def test_price_and_trip_type_come_from_the_preamble():
    it = parser.parse_google_flights(
        _read("test-case-gf-selected-trip-input.txt"), reference_date=REF)
    assert it.total_cost == Decimal("400")
    assert it.currency == "£"
    assert it.trip_type == "round trip"
    assert len(it.chunks) == 2


def test_rendered_header_carries_the_preamble_price():
    result = parser.parse_united_itinerary(
        _read("test-case-gf-selected-trip-input.txt"), reference_date=REF)
    assert result.splitlines()[0] == "- Google Flights itinerary: £400 round trip."


def test_slice_price_still_wins_over_the_preamble():
    """Search results state a price per slice; the preamble must not override
    it. gf-rt states £1,497 then £1,355, and last-slice-wins still applies."""
    it = parser.parse_google_flights(
        _read("test-case-gf-rt-input.txt"), reference_date=REF)
    assert it.total_cost == Decimal("1355")


def test_trip_type_runs_into_the_cabin():
    """The view prints 'Round tripEconomy' with no separator."""
    assert parser._gf_trip_type_anywhere("Round tripEconomy") == "round trip"
    assert parser._gf_trip_type_anywhere("One wayBusiness") == "one way"


def test_trip_type_does_not_match_a_longer_lowercase_word():
    assert parser._gf_trip_type_anywhere("one wayfarer") is None


def test_preamble_is_empty_when_the_text_starts_at_a_slice():
    text = _read("test-case-gf-5-input.txt")
    assert parser._gf_preamble(text) == ""


def test_loose_date_survives_a_glued_emissions_row():
    """The capture can drop the break after the date, leaving
    'Wed, Aug 26171 kg CO2e'. Splitting that is guesswork, so the date
    matcher tolerates the trailing junk instead."""
    block = "Departing flight\nWed, Aug 26171 kg CO2e\n"
    assert parser._gf_slice_base_date(block, REF) == date(2026, 8, 26)


def test_loose_date_falls_back_to_a_single_digit_day():
    """A greedy two-digit read of 'Aug 5171' yields day 51, which is not a
    real day; fall back to 5 rather than dropping the slice."""
    block = "Departing flight\nWed, Aug 5171 kg CO2e\n"
    assert parser._gf_slice_base_date(block, REF).day == 5
