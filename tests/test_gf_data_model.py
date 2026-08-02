"""New model fields and the shared segment-line renderer."""
from __future__ import annotations

from datetime import datetime

import parse as parser


def _seg(**overrides):
    base = dict(
        flight_number="355",
        dep_airport="LHR", dep_city="Heathrow",
        arr_airport="GVA", arr_city="Geneva",
        dep_datetime=datetime(2026, 8, 26, 14, 25),
        arr_datetime=datetime(2026, 8, 26, 17, 5),
    )
    base.update(overrides)
    return parser.Segment(**base)


def test_segment_airline_defaults_to_none():
    assert _seg().airline is None


def test_itinerary_currency_and_trip_type_defaults():
    it = parser.Itinerary(source="google_flights")
    assert it.currency == "$"
    assert it.trip_type is None


def test_segment_line_falls_back_to_ua_when_airline_absent():
    line = parser._render_segment_line(_seg(), [])
    assert line.startswith("    - LHR > GVA UA 355:")


def test_segment_line_uses_airline_when_present():
    line = parser._render_segment_line(_seg(airline="LX"), [])
    assert line.startswith("    - LHR > GVA LX 355:")


def test_google_flights_extras_are_cabin_and_aircraft():
    seg = _seg(airline="LX", fare_class="Economy", aircraft="Airbus A220-300")
    line = parser._render_segment_line_google_flights(seg)
    assert line.endswith("(Economy, Airbus A220-300).")


def test_google_flights_extras_omit_missing_values():
    seg = _seg(airline="LX", fare_class="Economy")
    line = parser._render_segment_line_google_flights(seg)
    assert line.endswith("(Economy).")
