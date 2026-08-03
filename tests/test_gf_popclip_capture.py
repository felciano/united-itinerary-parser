"""PopClip captures a selection through the macOS accessibility API, not the
clipboard, which flattens a Google Flights result card onto a single line.

The fixture here is a byte-exact capture taken from PopClip itself. A
clipboard copy of the same selection is properly line broken, so this failure
mode is invisible to any test written from a paste.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)

EXPECTED = """\
- Google Flights itinerary: LHR > HND, Thu Aug 27, £1,193 round trip
  - Heathrow (LHR) to Tokyo Haneda (HND) (via New Delhi (DEL)):
    - LHR > DEL AI 2018: dep LHR Thu Aug 27, 8:35 pm, arr DEL Fri 11:45 am (Economy, Boeing 787).
    - DEL > HND AI 358: dep DEL Fri Aug 28, 6:20 pm, arr HND Sat 5:55 am (Economy, Boeing 787)."""


def _capture() -> str:
    path = TEST_CASES / "test-case-gf-popclip-flattened-input.txt"
    return path.read_text(encoding="utf-8")


def test_capture_really_is_flattened():
    """Guard the fixture itself: if it ever gains newlines it stops testing
    the thing it exists to test."""
    raw = _capture()
    assert len(raw.splitlines()) == 1
    assert "·" in raw      # middle-dot field separator
    assert " " in raw      # non-breaking space
    assert "￼" in raw      # image / button placeholder


def test_flattened_capture_parses_end_to_end():
    result = parser.parse_united_itinerary(_capture(), reference_date=REF)
    assert result.rstrip("\n") == EXPECTED


def test_normalizer_leaves_line_broken_text_alone():
    """A clipboard paste must pass through untouched."""
    text = (TEST_CASES / "test-case-gf-5-input.txt").read_text(encoding="utf-8")
    assert parser._normalize_gf_flattened(text) == text


def test_normalizer_does_not_split_a_time_at_its_inner_colon():
    """'11:45' must not be cut into '1' and '1:45'."""
    flat = "Departure·Thu, Aug 27·11:45 AM+1Haneda Airport (HND)"
    lines = parser._normalize_gf_flattened(flat).splitlines()
    assert "11:45 AM+1Haneda Airport (HND)" in lines


def test_normalizer_closes_the_airline_row_after_the_flight_number():
    """Amenity text trailing the flight designator would defeat _GF_FLIGHT."""
    flat = "Departure·Air India·Economy·Boeing 787·AI 2018Free Wi-Fi"
    lines = parser._normalize_gf_flattened(flat).splitlines()
    assert "Air IndiaEconomyBoeing 787AI 2018" in lines


def test_both_capture_paths_agree():
    """The flattened capture and a line-broken paste of the same itinerary
    must render identically."""
    flat = parser.parse_united_itinerary(_capture(), reference_date=REF)
    lines = parser.parse_united_itinerary(
        parser._normalize_gf_flattened(_capture()), reference_date=REF)
    assert flat == lines
