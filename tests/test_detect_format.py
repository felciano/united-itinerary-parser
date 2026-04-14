"""Unit tests for detect_format."""
from __future__ import annotations

from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"


def _read(name: str) -> str:
    return (TEST_CASES / name).read_text(encoding="utf-8")


def test_email_sample_detects_as_email():
    text = _read("test-case-email-FQZ1B5-popclip-input.txt")
    assert parser.detect_format(text) == "email"


def test_email_nly82v_detects_as_email():
    text = _read("test-case-email-NLY82V-popclip-input.txt")
    assert parser.detect_format(text) == "email"


def test_reservation_ui_popclip_detects_as_reservation_ui():
    text = _read("test-case-6-popclip-input.txt")
    assert parser.detect_format(text) == "reservation_ui"


def test_reservation_ui_original_detects_as_reservation_ui():
    text = _read("test-case-6-input.txt")
    assert parser.detect_format(text) == "reservation_ui"


def test_empty_text_detects_as_unknown():
    assert parser.detect_format("") == "unknown"
