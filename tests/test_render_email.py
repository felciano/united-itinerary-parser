"""Tests for render_email."""
from __future__ import annotations

from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"

EXPECTED_NLY82V = """\
- Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
  - Washington (IAD) to London (LHR):
    - IAD > LHR UA 924: dep IAD Wed Mar 11, 11:15 pm, arr LHR Thu 10:50 am (Economy V, seat 35F)."""

EXPECTED_FQZ1B5 = """\
- Itinerary FQZ1B5: $2,564.60 + $1,100.00 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.
  - London (LHR) to Punta Cana (PUJ) (via Newark (EWR)):
    - LHR > EWR UA 17: dep LHR Sun Apr 26, 10:25 am, arr EWR 1:20 pm (Economy W, seat 33K).
    - EWR > PUJ UA 1514: dep EWR Mon Apr 27, 8:11 am, arr PUJ 12:15 pm (Economy W, seat 09D).
  - Punta Cana (PUJ) to London (LHR) (via Houston (IAH)):
    - PUJ > IAH UA 524: dep PUJ Thu Apr 30, 2:20 pm, arr IAH 6:04 pm (Economy S, seat 09D).
    - IAH > LHR UA 5: dep IAH Thu Apr 30, 8:05 pm, arr LHR Fri 11:35 am (Economy S, seat 32G)."""


def test_render_email_NLY82V():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert parser.render_email(it) == EXPECTED_NLY82V


def test_render_email_FQZ1B5():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert parser.render_email(it) == EXPECTED_FQZ1B5
