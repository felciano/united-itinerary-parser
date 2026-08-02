"""The line-shape regexes that carry all Google Flights signal."""
from __future__ import annotations

import pytest

import parse as parser


@pytest.mark.parametrize("line,expected", [
    ("6:15 AMLondon Stansted Airport (STN)",
     ("6", "15", "AM", None, "London Stansted Airport", "STN")),
    ("5:15 PM+1Haneda Airport (HND)",
     ("5", "15", "PM", "1", "Haneda Airport", "HND")),
    ("12:10 PMIstanbul Airport (IST)",
     ("12", "10", "PM", None, "Istanbul Airport", "IST")),
    ("7:05 PM+1Kansai International Airport (KIX)",
     ("7", "05", "PM", "1", "Kansai International Airport", "KIX")),
])
def test_time_airport_anchor(line, expected):
    assert parser._GF_TIME_AIRPORT.match(line).groups() == expected


@pytest.mark.parametrize("line", [
    "Below average legroom (29 in)",
    "Average legroom (31 in)",
    "1 hr 55 min layoverOsaka (KIX)",
    "Emissions estimate: 226 kg CO2e",
    "Travel time: 3 hr 55 min",
])
def test_time_airport_anchor_ignores_noise(line):
    assert parser._GF_TIME_AIRPORT.match(line) is None


@pytest.mark.parametrize("line,expected", [
    ("SWISSEconomyAirbus A220-300 PassengerLX 355",
     ("SWISS", "Economy", "Airbus A220-300 Passenger", "LX", "355")),
    ("ANAEconomyBoeing 737NH 98",
     ("ANA", "Economy", "Boeing 737", "NH", "98")),
    ("Turkish AirlinesEconomyBoeing 737TK 1246",
     ("Turkish Airlines", "Economy", "Boeing 737", "TK", "1246")),
    ("ITAEconomyAirbus A350AZ 793",
     ("ITA", "Economy", "Airbus A350", "AZ", "793")),
    ("ITAEconomyAirbus A320neoAZ 203",
     ("ITA", "Economy", "Airbus A320neo", "AZ", "203")),
])
def test_flight_anchor(line, expected):
    assert parser._GF_FLIGHT.match(line).groups() == expected


def test_flight_anchor_prefers_premium_economy_over_economy():
    line = "SWISSPremium economyBoeing 777LX 41"
    assert parser._GF_FLIGHT.match(line).group(2) == "Premium economy"


@pytest.mark.parametrize("line", [
    "Plane and crew by ANA Wings",
    "Often delayed by 30+ min",
    "In-seat power & USB outlets",
    "Stream media to your device",
])
def test_flight_anchor_ignores_noise(line):
    assert parser._GF_FLIGHT.match(line) is None


@pytest.mark.parametrize("line,city,iata", [
    ("1 hr 25 min layoverGeneva (GVA)", "Geneva", "GVA"),
    ("10 hr 35 min layoverRome (FCO)Long layover", "Rome", "FCO"),
    ("14 hr 15 min layoverIstanbul (IST)Long layover", "Istanbul", "IST"),
    ("1 hr 55 min layoverOsaka (KIX)", "Osaka", "KIX"),
])
def test_layover_anchor(line, city, iata):
    match = parser._GF_LAYOVER.search(line)
    assert match.group(1) == city
    assert match.group(2) == iata


def test_slice_header_anchor():
    assert parser._GF_SLICE_HEADER.match("Departure")
    assert parser._GF_SLICE_HEADER.match("Return")
    assert parser._GF_SLICE_HEADER.match("Departures") is None


def test_slice_date_anchor():
    assert parser._GF_SLICE_DATE.match("Wed, Aug 26").groups() == (
        "Wed", "Aug", "26")


@pytest.mark.parametrize("line,symbol,amount", [
    ("£301", "£", "301"),
    ("£1,387", "£", "1,387"),
    ("$1,234.56", "$", "1,234.56"),
])
def test_price_anchor(line, symbol, amount):
    match = parser._GF_PRICE.match(line)
    assert match.group(1) == symbol
    assert match.group(2) == amount


@pytest.mark.parametrize("line", [
    "171 kg CO2e",
    "+82% emissions",
    "round trip",
    "Avoids as much CO2e as 791 trees absorb in a day",
])
def test_price_anchor_ignores_noise(line):
    assert parser._GF_PRICE.match(line) is None


@pytest.mark.parametrize("raw,expected", [
    ("Airbus A220-300 Passenger", "Airbus A220-300"),
    ("Boeing 777", "Boeing 777"),
    ("Airbus A320neo", "Airbus A320neo"),
])
def test_clean_aircraft(raw, expected):
    assert parser._clean_gf_aircraft(raw) == expected
