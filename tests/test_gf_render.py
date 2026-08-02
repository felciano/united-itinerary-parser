"""render_google_flights output."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)

EXPECTED_GF5 = """\
- Google Flights itinerary: £1,387 round trip.
  - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737)."""


def test_render_gf5():
    text = (TEST_CASES / "test-case-gf-5-input.txt").read_text(encoding="utf-8")
    it = parser.parse_google_flights(text, reference_date=REF)
    assert parser.render_google_flights(it) == EXPECTED_GF5


def test_header_without_price_or_trip_type():
    it = parser.Itinerary(source="google_flights")
    assert parser._render_itinerary_header_google_flights(it) == (
        "- Google Flights itinerary:")


def test_header_with_price_only():
    it = parser.Itinerary(
        source="google_flights", total_cost=Decimal("301"), currency="£")
    assert parser._render_itinerary_header_google_flights(it) == (
        "- Google Flights itinerary: £301.")
