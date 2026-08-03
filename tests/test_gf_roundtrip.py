"""Round trips, in the selected-trip view.

This view differs from search results in three ways that each broke parsing:
slices are headed "Departing flight"/"Returning flight" rather than
"Departure"/"Return", the airline block is split across three lines instead of
concatenated onto one, and no price is shown at all.

Both captures below are real: one copied to the clipboard, one taken from
PopClip's accessibility-API capture of the same trip. They must agree.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)

EXPECTED = """\
- Google Flights itinerary:
  - Heathrow (LHR) to Biarritz (BIQ) (via Geneva (GVA)):
    - LHR > GVA LX 355: dep LHR Wed Aug 26, 2:25 pm, arr GVA 5:05 pm (Economy, Airbus A220-300).
    - GVA > BIQ LX 2332: dep GVA Wed Aug 26, 6:30 pm, arr BIQ 7:50 pm (Economy, Airbus A220-300).
  - Biarritz (BIQ) to Heathrow (LHR) (via Geneva (GVA)):
    - BIQ > GVA LX 2333: dep BIQ Sun Aug 30, 8:45 am, arr GVA 10:05 am (Economy, Airbus A220-300).
    - GVA > LHR LX 354: dep GVA Sun Aug 30, 12:55 pm, arr LHR 1:40 pm (Economy, Airbus A220-300)."""


def _read(name: str) -> str:
    return (TEST_CASES / name).read_text(encoding="utf-8")


def test_clipboard_roundtrip():
    result = parser.parse_united_itinerary(
        _read("test-case-gf-roundtrip-input.txt"), reference_date=REF)
    assert result.rstrip("\n") == EXPECTED


def test_popclip_roundtrip():
    result = parser.parse_united_itinerary(
        _read("test-case-gf-popclip-roundtrip-input.txt"), reference_date=REF)
    assert result.rstrip("\n") == EXPECTED


def test_both_capture_methods_agree():
    clip = parser.parse_united_itinerary(
        _read("test-case-gf-roundtrip-input.txt"), reference_date=REF)
    popclip = parser.parse_united_itinerary(
        _read("test-case-gf-popclip-roundtrip-input.txt"), reference_date=REF)
    assert clip == popclip


def test_popclip_roundtrip_fixture_is_flattened():
    """Guard the fixture: it only tests the accessibility-API form while it
    stays on one line."""
    raw = _read("test-case-gf-popclip-roundtrip-input.txt")
    assert len(raw.splitlines()) == 1
    assert "·" in raw


def test_selected_trip_slice_headers_are_recognised():
    for header in ("Departing flight", "Returning flight"):
        assert parser._GF_SLICE_HEADER.match(header), header


def test_split_airline_block_is_rejoined():
    text = "SWISS\nEconomy\nAirbus A220-300 PassengerLX 355\nnoise"
    joined = parser._join_gf_flight_rows(text).splitlines()
    assert "SWISSEconomyAirbus A220-300 PassengerLX 355" in joined
    assert parser._GF_FLIGHT.match(joined[0])


def test_join_leaves_an_already_concatenated_block_alone():
    text = "SWISSEconomyAirbus A220-300 PassengerLX 355\nnoise"
    assert parser._join_gf_flight_rows(text) == text


def test_no_price_yields_a_header_without_a_trailing_period():
    """This view shows no fare, so the header must not end in a stray dot."""
    result = parser.parse_united_itinerary(
        _read("test-case-gf-roundtrip-input.txt"), reference_date=REF)
    assert result.splitlines()[0] == "- Google Flights itinerary:"
