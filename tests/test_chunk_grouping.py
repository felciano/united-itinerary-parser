"""Unit tests for group_into_chunks."""
from __future__ import annotations

from datetime import datetime

import parse as parser


def _seg(flight: str, dep: str, arr: str, dep_dt: datetime, arr_dt: datetime):
    return parser.Segment(
        flight_number=flight, dep_airport=dep, dep_city=None,
        arr_airport=arr, arr_city=None,
        dep_datetime=dep_dt, arr_datetime=arr_dt,
    )


def test_empty_list_produces_no_chunks():
    assert parser.group_into_chunks([]) == []


def test_single_segment_is_one_chunk():
    s = _seg("924", "IAD", "LHR",
             datetime(2026, 3, 11, 23, 15), datetime(2026, 3, 12, 10, 50))
    chunks = parser.group_into_chunks([s])
    assert len(chunks) == 1
    assert chunks[0].segments == [s]


def test_connection_within_24h_same_chunk():
    s1 = _seg("17", "LHR", "EWR",
              datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20))
    s2 = _seg("1514", "EWR", "PUJ",
              datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 1
    assert chunks[0].segments == [s1, s2]


def test_stopover_over_24h_new_chunk():
    s1 = _seg("1514", "EWR", "PUJ",
              datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15))
    s2 = _seg("524", "PUJ", "IAH",
              datetime(2026, 4, 30, 14, 20), datetime(2026, 4, 30, 18, 4))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 2


def test_airport_mismatch_new_chunk():
    s1 = _seg("17", "LHR", "EWR",
              datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20))
    s2 = _seg("X", "JFK", "LAX",
              datetime(2026, 4, 26, 14, 0), datetime(2026, 4, 26, 19, 0))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 2


def test_exactly_24h_boundary_same_chunk():
    s1 = _seg("A", "AAA", "BBB",
              datetime(2026, 1, 1, 10, 0), datetime(2026, 1, 1, 12, 0))
    s2 = _seg("B", "BBB", "CCC",
              datetime(2026, 1, 2, 12, 0), datetime(2026, 1, 2, 14, 0))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 1


def test_real_itinerary_FQZ1B5_shape():
    s = [
        _seg("17", "LHR", "EWR",
             datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20)),
        _seg("1514", "EWR", "PUJ",
             datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15)),
        _seg("524", "PUJ", "IAH",
             datetime(2026, 4, 30, 14, 20), datetime(2026, 4, 30, 18, 4)),
        _seg("5", "IAH", "LHR",
             datetime(2026, 4, 30, 20, 5), datetime(2026, 5, 1, 11, 35)),
    ]
    chunks = parser.group_into_chunks(s)
    assert len(chunks) == 2
    assert [seg.flight_number for seg in chunks[0].segments] == ["17", "1514"]
    assert [seg.flight_number for seg in chunks[1].segments] == ["524", "5"]
