"""Tests for parse_email itinerary-level field extraction."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"


def test_parse_email_NLY82V_itinerary_fields():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert it.source == "email"
    assert it.confirmation_number == "NLY82V"
    assert it.eticket_number == "0162379511080"
    assert it.total_cost == Decimal("556.50")
    assert it.upgrade_fees is None
    assert it.accrual_award_miles == 4707
    assert it.accrual_pqp == 523
    assert it.accrual_pqf == 1


def test_parse_email_FQZ1B5_itinerary_fields():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert it.confirmation_number == "FQZ1B5"
    assert it.eticket_number == "0162389632983"
    assert it.total_cost == Decimal("2564.60")
    assert it.upgrade_fees == Decimal("1100.00")
    assert it.accrual_award_miles == 21510
    assert it.accrual_pqp == 2151
    assert it.accrual_pqf == 4


def test_parse_email_FQZ1B5_chunks():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert len(it.chunks) == 2
    assert [s.flight_number for s in it.chunks[0].segments] == ["17", "1514"]
    assert [s.flight_number for s in it.chunks[1].segments] == ["524", "5"]
