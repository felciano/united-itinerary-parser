"""Year inference for Google Flights dates, which carry no year."""
from __future__ import annotations

from datetime import date

import parse as parser

REF = date(2026, 8, 2)


def test_matches_weekday_in_current_year():
    # 2026-08-26 is a Wednesday
    assert parser._infer_year(8, 26, "Wed", REF) == 2026


def test_matches_weekday_later_in_current_year():
    # 2026-08-30 is a Sunday
    assert parser._infer_year(8, 30, "Sun", REF) == 2026


def test_rolls_into_next_year_when_date_already_passed():
    # 2027-01-03 is a Sunday; 2026-01-03 is before the reference
    assert parser._infer_year(1, 3, "Sun", REF) == 2027


def test_spans_an_eleven_year_gap():
    # Aug 26 is Wednesday in 2026, then not again until 2037
    assert parser._infer_year(8, 26, "Wed", date(2027, 1, 1)) == 2037


def test_unknown_weekday_falls_back_to_first_candidate():
    assert parser._infer_year(8, 26, "Xxx", REF) == 2026


def test_skips_feb_29_in_non_leap_years():
    # 2028-02-29 is a Tuesday; 2027 has no Feb 29
    assert parser._infer_year(2, 29, "Tue", date(2027, 1, 1)) == 2028
