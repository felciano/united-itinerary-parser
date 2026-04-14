"""Unit tests for the Itinerary/Chunk/Segment data model."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import parse as parser


def test_segment_construction():
    s = parser.Segment(
        flight_number="17",
        dep_airport="LHR",
        dep_city="London",
        arr_airport="EWR",
        arr_city="Newark",
        dep_datetime=datetime(2026, 4, 26, 10, 25),
        arr_datetime=datetime(2026, 4, 26, 13, 20),
        fare_class="Economy W",
        seat="33K",
        aircraft=None,
        duration=None,
    )
    assert s.dep_airport == "LHR"
    assert s.seat == "33K"


def test_chunk_construction():
    s = parser.Segment(
        flight_number="924", dep_airport="IAD", dep_city="Washington",
        arr_airport="LHR", arr_city="London",
        dep_datetime=datetime(2026, 3, 11, 23, 15),
        arr_datetime=datetime(2026, 3, 12, 10, 50),
        fare_class="Economy V", seat="35F", aircraft=None, duration=None,
    )
    c = parser.Chunk(segments=[s], total_duration=None)
    assert len(c.segments) == 1


def test_itinerary_construction():
    it = parser.Itinerary(
        source="email",
        chunks=[],
        total_cost=Decimal("556.50"),
        miles=None,
        plus_points=None,
        confirmation_number="NLY82V",
        eticket_number="0162379511080",
        upgrade_fees=None,
        accrual_award_miles=4707,
        accrual_pqp=523,
        accrual_pqf=1,
    )
    assert it.confirmation_number == "NLY82V"
