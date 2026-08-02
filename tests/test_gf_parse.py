"""parse_google_flights: slices, segments, dates, price."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)


def _gf5():
    return (TEST_CASES / "test-case-gf-5-input.txt").read_text(encoding="utf-8")


def test_single_slice_yields_one_chunk():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    assert it.source == "google_flights"
    assert len(it.chunks) == 1


def test_three_segments_in_order():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    segments = it.chunks[0].segments
    assert [s.flight_number for s in segments] == ["1246", "86", "98"]
    assert [s.airline for s in segments] == ["TK", "TK", "NH"]


def test_airports_and_resolved_city_names():
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].dep_airport == "STN"
    assert segments[0].dep_city == "London Stansted"
    assert segments[1].arr_airport == "KIX"
    assert segments[1].arr_city == "Osaka"       # tier 2, from a layover line
    assert segments[2].arr_city == "Tokyo Haneda"       # tier 1, curated map


def test_day_offset_counts_from_the_slice_date_not_cumulatively():
    """All three +1 markers mean Aug 27, even across two layovers."""
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].dep_datetime == datetime(2026, 8, 26, 6, 15)
    assert segments[0].arr_datetime == datetime(2026, 8, 26, 12, 10)
    assert segments[1].dep_datetime == datetime(2026, 8, 27, 2, 25)
    assert segments[1].arr_datetime == datetime(2026, 8, 27, 19, 5)
    assert segments[2].dep_datetime == datetime(2026, 8, 27, 21, 0)
    assert segments[2].arr_datetime == datetime(2026, 8, 27, 22, 20)


def test_cabin_and_aircraft():
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].fare_class == "Economy"
    assert segments[0].aircraft == "Boeing 737"
    assert segments[1].aircraft == "Boeing 787"


def test_price_currency_and_trip_type():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    assert it.currency == "£"
    assert it.total_cost == Decimal("1387")
    assert it.trip_type == "round trip"


def test_two_slices_yield_two_chunks_and_the_last_price():
    text = (
        "Departure\nWed, Aug 26\n£1,497\nround trip\n"
        "7:00 PMHeathrow Airport (LHR)\n"
        "Travel time: 14 hr 15 minOvernight\n"
        "5:15 PM+1Haneda Airport (HND)\n"
        "ANAEconomyBoeing 777NH 212\n"
        "Return\nSun, Aug 30\n£1,355\nround trip\n"
        "12:40 PMHaneda Airport (HND)\n"
        "Travel time: 14 hr 45 min\n"
        "8:25 PMLeonardo da Vinci International Airport (FCO)\n"
        "ITAEconomyAirbus A350AZ 793\n"
    )
    it = parser.parse_google_flights(text, reference_date=REF)
    assert len(it.chunks) == 2
    assert it.total_cost == Decimal("1355")


def test_no_slice_header_yields_no_chunks():
    assert parser.parse_google_flights("nothing here", reference_date=REF).chunks == []


def test_impossible_date_is_skipped_not_raised():
    """A mangled paste must not raise a traceback at the user."""
    text = (
        "Departure\nMon, Apr 31\n£100\nround trip\n"
        "6:15 AMHeathrow Airport (LHR)\n"
        "Travel time: 1 hr\n"
        "7:15 AMGeneva Airport (GVA)\n"
        "SWISSEconomyAirbus A220-300 PassengerLX 1\n"
    )
    it = parser.parse_google_flights(text, reference_date=REF)
    assert it.chunks == []


def test_slice_header_without_segments_renders_nothing():
    text = "Departure\nWed, Aug 26\n£251\nround trip\n"
    assert parser.parse_united_itinerary(text, reference_date=REF) == ""


def test_unparseable_text_renders_nothing():
    assert parser.parse_united_itinerary("Travel time: kg CO2e") == ""
