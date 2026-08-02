"""Chunk-header place names: curated map, then layover city, then stripped."""
from __future__ import annotations

import parse as parser


def test_tier_one_curated_map_wins():
    assert parser._resolve_place_name("HND", "Haneda Airport", {}) == "Tokyo"
    assert parser._resolve_place_name(
        "FCO", "Leonardo da Vinci International Airport", {}) == "Rome"


def test_tier_one_beats_a_conflicting_layover_city():
    resolved = parser._resolve_place_name(
        "FCO", "Leonardo da Vinci International Airport", {"FCO": "Fiumicino"})
    assert resolved == "Rome"


def test_tier_two_layover_city():
    resolved = parser._resolve_place_name(
        "KIX", "Kansai International Airport", {"KIX": "Osaka"})
    assert resolved == "Osaka"


def test_tier_three_strips_airport_suffix():
    assert parser._resolve_place_name("LHR", "Heathrow Airport", {}) == "Heathrow"
    assert parser._resolve_place_name(
        "STN", "London Stansted Airport", {}) == "London Stansted"
    assert parser._resolve_place_name(
        "LCY", "London City Airport", {}) == "London City"


def test_lhr_is_deliberately_unmapped():
    """Heathrow reads better than London, and LHR/LCY must stay distinct."""
    assert "LHR" not in parser._IATA_CITY


def test_harvest_layover_cities():
    text = (
        "14 hr 15 min layoverIstanbul (IST)Long layover\n"
        "noise\n"
        "1 hr 55 min layoverOsaka (KIX)\n"
    )
    assert parser._harvest_layover_cities(text) == {
        "IST": "Istanbul", "KIX": "Osaka"}


def test_harvest_returns_empty_for_nonstop():
    assert parser._harvest_layover_cities("no layovers here") == {}
