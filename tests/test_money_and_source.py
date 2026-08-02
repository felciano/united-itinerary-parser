"""Price formatting and the source qualifier on itinerary headers."""
from __future__ import annotations

from decimal import Decimal

import parse as parser


def test_fmt_money_drops_decimals():
    assert parser._fmt_money(Decimal("2564.60")) == "$2,565"


def test_fmt_money_rounds_half_up():
    assert parser._fmt_money(Decimal("556.50")) == "$557"


def test_fmt_money_rounds_down_below_half():
    assert parser._fmt_money(Decimal("3248.25")) == "$3,248"


def test_fmt_money_whole_amount_unchanged():
    assert parser._fmt_money(Decimal("2740.00")) == "$2,740"


def test_fmt_money_honours_currency_symbol():
    assert parser._fmt_money(Decimal("1387"), "£") == "£1,387"


def test_source_labels():
    assert parser._SOURCE_LABEL["reservation_ui"] == "United.com"
    assert parser._SOURCE_LABEL["email"] == "United.com"
    assert parser._SOURCE_LABEL["google_flights"] == "Google Flights"
