"""Route and date summaries on the itinerary header line."""
from __future__ import annotations

from datetime import datetime

import parse as parser


def test_route_collapses_a_there_and_back_trip():
    assert parser._summarize_route(["LHR", "BIQ", "LHR"]) == "LHR <-> BIQ"


def test_route_chains_a_one_way():
    assert parser._summarize_route(["STN", "HND"]) == "STN > HND"


def test_route_chains_multi_city_rather_than_collapsing_it():
    """Three chunks returning to the origin is not a round trip, and must not
    be shown as one."""
    assert parser._summarize_route(
        ["LHR", "PUJ", "SFO", "LHR"]) == "LHR > PUJ > SFO > LHR"


def test_route_chains_two_chunks_that_do_not_return_home():
    assert parser._summarize_route(["LHR", "HND", "LCY"]) == "LHR > HND > LCY"


def test_route_needs_at_least_two_stops():
    assert parser._summarize_route(["LHR"]) is None
    assert parser._summarize_route([]) is None


def test_dates_render_as_a_range():
    assert parser._summarize_dates(
        datetime(2026, 8, 26, 14, 25),
        datetime(2026, 8, 30, 8, 45)) == "Wed Aug 26 - Sun Aug 30"


def test_dates_collapse_when_the_trip_starts_and_ends_the_same_day():
    same = datetime(2026, 8, 26, 6, 15)
    assert parser._summarize_dates(same, same) == "Wed Aug 26"


def test_summarize_itinerary_is_empty_without_chunks():
    it = parser.Itinerary(source="google_flights")
    assert parser._summarize_itinerary(it) == (None, None)


def test_reservation_ui_summary_is_recovered_from_rendered_lines():
    """The reservation-UI path never populates the dataclasses, so route and
    dates are read back out of the lines it already emitted."""
    lines = [
        "  - LHR > EWR > PUJ UA 921/1514: dep LHR Sat Apr 25, 6:00 pm, arr EWR 9:20 pm.",
        "  - PUJ > EWR > SFO UA 1526/2115: dep PUJ Thu Apr 30, 4:19 pm, arr EWR 8:31 pm.",
        "  - SFO > LHR UA 901: dep SFO Sun May 3, 12:50 pm, arr LHR Mon 7:25 am.",
    ]
    route, dates = parser._summarize_reservation_ui(lines)
    assert route == "LHR > PUJ > SFO > LHR"
    assert dates == "Sat Apr 25 - Sun May 3"


def test_reservation_ui_summary_collapses_a_round_trip():
    lines = [
        "  - LHR > SFO UA 900: dep LHR Fri Apr 11, 10:05 am, arr SFO 1:20 pm.",
        "  - SFO > LHR UA 901: dep SFO Wed Apr 16, 12:50 pm, arr LHR Thu 7:25 am.",
    ]
    route, dates = parser._summarize_reservation_ui(lines)
    assert route == "LHR <-> SFO"
    assert dates == "Fri Apr 11 - Wed Apr 16"


def test_reservation_ui_summary_ignores_unrecognised_lines():
    assert parser._summarize_reservation_ui(["- United.com itinerary: $1"]) == (
        None, None)


def test_no_header_ends_with_a_period():
    """The trailing period was dropped across all three formats."""
    from datetime import date
    from pathlib import Path
    cases = Path(__file__).resolve().parent.parent / "test-cases"
    for name in ("test-case-6-popclip-input.txt",
                 "test-case-email-NLY82V-popclip-input.txt",
                 "test-case-gf-5-input.txt"):
        text = (cases / name).read_text(encoding="utf-8")
        header = parser.parse_united_itinerary(
            text, reference_date=date(2026, 8, 2)).splitlines()[0]
        assert not header.endswith("."), header
