"""Parse email flight blocks into Segments."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"


def test_parse_email_segments_NLY82V_single_flight():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    assert len(segments) == 1
    s = segments[0]
    assert s.flight_number == "924"
    assert s.dep_airport == "IAD"
    assert s.dep_city == "Washington"
    assert s.arr_airport == "LHR"
    assert s.arr_city == "London"
    assert s.dep_datetime == datetime(2026, 3, 11, 23, 15)
    assert s.arr_datetime == datetime(2026, 3, 12, 10, 50)
    assert s.fare_class == "Economy V"


def test_parse_email_segments_FQZ1B5_multi_flight():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    assert [s.flight_number for s in segments] == ["17", "1514", "524", "5"]
    assert segments[0].dep_city == "London"
    # Newark, NJ/New York, NY, US (EWR) → "Newark" (text before first comma)
    assert segments[0].arr_city == "Newark"
    assert segments[0].arr_airport == "EWR"
    # PUJ→IAH 2:20 PM → 6:04 PM same day
    assert segments[2].dep_datetime == datetime(2026, 4, 30, 14, 20)
    assert segments[2].arr_datetime == datetime(2026, 4, 30, 18, 4)
    # IAH→LHR crosses midnight: Thu 8:05 PM → Fri 11:35 AM
    assert segments[3].dep_datetime == datetime(2026, 4, 30, 20, 5)
    assert segments[3].arr_datetime == datetime(2026, 5, 1, 11, 35)
    # Fare class codes
    assert segments[0].fare_class == "Economy W"
    assert segments[2].fare_class == "Economy S"
