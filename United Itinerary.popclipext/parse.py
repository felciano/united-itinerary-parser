#!/usr/bin/env python3
"""PopClip extension to parse United Airlines itineraries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional


@dataclass
class Segment:
    flight_number: str
    dep_airport: str
    dep_city: Optional[str]
    arr_airport: str
    arr_city: Optional[str]
    dep_datetime: datetime
    arr_datetime: datetime
    fare_class: Optional[str] = None
    seat: Optional[str] = None
    aircraft: Optional[str] = None
    duration: Optional[timedelta] = None
    airline: Optional[str] = None


@dataclass
class Chunk:
    segments: list
    total_duration: Optional[timedelta] = None


@dataclass
class Itinerary:
    source: str  # "reservation_ui" | "email" | "google_flights"
    chunks: list = field(default_factory=list)
    total_cost: Optional[Decimal] = None
    miles: Optional[int] = None
    plus_points: Optional[int] = None
    confirmation_number: Optional[str] = None
    eticket_number: Optional[str] = None
    upgrade_fees: Optional[Decimal] = None
    accrual_award_miles: Optional[int] = None
    accrual_pqp: Optional[int] = None
    accrual_pqf: Optional[int] = None
    currency: str = "$"
    trip_type: Optional[str] = None


CHUNK_GAP_THRESHOLD = timedelta(hours=24)

_SOURCE_LABEL = {
    "reservation_ui": "United.com",
    "email": "United.com",
    "google_flights": "Google Flights",
}


def group_into_chunks(segments):
    """Group consecutive segments into trip chunks.

    Two segments belong to the same chunk iff the first's arrival airport
    matches the second's departure airport AND the time gap between them
    is within [0, 24] hours. Otherwise the second starts a new chunk.
    """
    if not segments:
        return []

    chunks = []
    current = [segments[0]]

    for prev, curr in zip(segments, segments[1:]):
        gap = curr.dep_datetime - prev.arr_datetime
        same_chunk = (
            prev.arr_airport == curr.dep_airport
            and timedelta(0) <= gap <= CHUNK_GAP_THRESHOLD
        )
        if same_chunk:
            current.append(curr)
        else:
            chunks.append(Chunk(segments=current))
            current = [curr]

    chunks.append(Chunk(segments=current))
    return chunks


def detect_format(text):
    """Classify the input as 'google_flights', 'email', 'reservation_ui',
    or 'unknown'.

    Google Flights signatures: both 'Travel time:' and 'kg CO2e' appear.
    Checked first, since it takes precedence over the other two.

    Email signatures: both 'Thank you for choosing United' and
    'Confirmation Number:' appear (the combination rarely occurs
    coincidentally in reservation-UI text).

    Reservation-UI signatures: any of 'Flight selection list',
    'Aircraft type:', or 'Duration:' appears.

    If google_flights matches, it wins. Otherwise, if email matches, it
    wins (more specific than reservation-UI). If none match, returns
    'unknown'.
    """
    is_google_flights = "Travel time:" in text and "kg CO2e" in text
    is_email = (
        "Thank you for choosing United" in text
        and "Confirmation Number:" in text
    )
    is_reservation_ui = (
        "Flight selection list" in text
        or "Aircraft type:" in text
        or "Duration:" in text
    )
    if is_google_flights:
        return "google_flights"
    if is_email:
        return "email"
    if is_reservation_ui:
        return "reservation_ui"
    return "unknown"


# --- Google Flights parser -----------------------------------------------

_WEEKDAY_NUM = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
}

# A month/day returns to the same weekday on an irregular 5-, 6- or 11-year
# cycle, so the window has to clear 11 (Wed Aug 26 is 2026, then 2037).
_YEAR_SEARCH_WINDOW = 12


def _infer_year(month, day, weekday, reference):
    """Infer the year of a Google Flights date, which omits it.

    Returns the year of the first date on or after `reference` matching
    `month`/`day` whose weekday agrees with `weekday`. When no weekday
    matches — or `weekday` is unrecognized — returns the year of the
    earliest candidate on or after `reference`.
    """
    target = _WEEKDAY_NUM.get(weekday)
    fallback = None
    for year in range(reference.year, reference.year + _YEAR_SEARCH_WINDOW):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue  # Feb 29 in a non-leap year
        if candidate < reference:
            continue
        if fallback is None:
            fallback = year
        if target is None or candidate.weekday() == target:
            return year
    return fallback if fallback is not None else reference.year


_GF_SLICE_HEADER = re.compile(r"^(Departure|Return)$")
_GF_SLICE_DATE = re.compile(r"^([A-Z][a-z]{2}),\s*([A-Z][a-z]{2})\s+(\d{1,2})$")
_GF_PRICE = re.compile(r"^(\D{1,3}?)\s*([\d,]+(?:\.\d{2})?)$")
_GF_TIME_AIRPORT = re.compile(
    r"^(\d{1,2}):(\d{2})\s*([AP]M)(?:\+(\d+))?(.+?)\s*\(([A-Z]{3})\)$"
)
_GF_FLIGHT = re.compile(
    r"^(.+?)(Premium economy|Economy|Business|First)(.*?)"
    r"([A-Z0-9]{2})\s(\d{1,4})$"
)
_GF_LAYOVER = re.compile(r"layover(.+?)\s*\(([A-Z]{3})\)")


def _clean_gf_aircraft(raw):
    """Strip the trailing ' Passenger' Google appends to some airframes."""
    return re.sub(r"\s+Passenger$", "", raw.strip())


# Curated exception list, not a derived rule: only airports whose Google
# Flights name reads poorly as a label AND which no layover line names.
# LHR is deliberately absent -- 'Heathrow' beats 'London', and a London
# round trip out of LHR into LCY must keep its endpoints distinct.
_IATA_CITY = {
    "HND": "Tokyo",   # "Haneda Airport"
    "FCO": "Rome",    # "Leonardo da Vinci International Airport"
}


def _harvest_layover_cities(text):
    """Map IATA code to city name using every layover line in the paste."""
    cities = {}
    for match in _GF_LAYOVER.finditer(text):
        cities.setdefault(match.group(2), match.group(1).strip())
    return cities


def _resolve_place_name(iata, airport_name, layover_cities):
    """Resolve a chunk-header label for one airport."""
    if iata in _IATA_CITY:
        return _IATA_CITY[iata]
    if iata in layover_cities:
        return layover_cities[iata]
    return re.sub(r"\s+Airport$", "", airport_name.strip())


_MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_GF_TRIP_TYPES = ("round trip", "one way")


def _parse_gf_slices(text):
    """Split a paste into one block per Departure/Return header."""
    lines = text.splitlines()
    starts = [
        i for i, line in enumerate(lines)
        if _GF_SLICE_HEADER.match(line.strip())
    ]
    return [
        "\n".join(lines[start:(starts[i + 1] if i + 1 < len(starts) else len(lines))])
        for i, start in enumerate(starts)
    ]


def _gf_slice_base_date(block, not_before):
    """Read the slice's date line and resolve its year forward."""
    for line in block.splitlines():
        match = _GF_SLICE_DATE.match(line.strip())
        if not match:
            continue
        weekday, month_abbr, day = match.groups()
        month = _MONTH_ABBR.get(month_abbr)
        if month is None:
            return None
        year = _infer_year(month, int(day), weekday, not_before)
        try:
            return date(year, month, int(day))
        except ValueError:
            return None
    return None


def _gf_slice_header_lines(block):
    """Lines before the first segment, where price and trip type live."""
    header = []
    for line in block.splitlines():
        if _GF_TIME_AIRPORT.match(line.strip()):
            break
        header.append(line.strip())
    return header


def _gf_slice_price(block):
    """Return (currency_symbol, amount) for the slice, or (None, None)."""
    for line in _gf_slice_header_lines(block):
        match = _GF_PRICE.match(line)
        if match:
            symbol = match.group(1).strip()
            amount = Decimal(match.group(2).replace(",", ""))
            return symbol, amount
    return None, None


def _gf_slice_trip_type(block):
    """Return 'round trip' / 'one way' as printed, or None."""
    for line in _gf_slice_header_lines(block):
        if line in _GF_TRIP_TYPES:
            return line
    return None


def _parse_gf_segments(block, base_date, layover_cities):
    """Parse one slice into Segments.

    Time+airport lines arrive in departure/arrival pairs; the airline line
    that follows a pair closes the segment. Everything else is noise and is
    skipped by not matching an anchor.
    """
    segments = []
    pending = []
    for raw in block.splitlines():
        line = raw.strip()
        stop = _GF_TIME_AIRPORT.match(line)
        if stop:
            pending.append(_gf_stop(stop, base_date))
            continue
        flight = _GF_FLIGHT.match(line)
        if flight and len(pending) >= 2:
            segments.append(
                _gf_segment(flight, pending[-2], pending[-1], layover_cities)
            )
            pending = []
    return segments


def _gf_stop(match, base_date):
    """Turn a time+airport match into (datetime, airport_name, iata)."""
    hour, minute, meridiem, offset, name, iata = match.groups()
    hh, mm = _to_24h(int(hour), int(minute), meridiem)
    day = base_date + timedelta(days=int(offset or 0))
    return datetime(day.year, day.month, day.day, hh, mm), name.strip(), iata


def _gf_segment(flight, dep, arr, layover_cities):
    """Build a Segment from a flight-line match and its two stops."""
    _airline_name, cabin, aircraft, code, number = flight.groups()
    return Segment(
        flight_number=number,
        airline=code,
        dep_airport=dep[2],
        dep_city=_resolve_place_name(dep[2], dep[1], layover_cities),
        arr_airport=arr[2],
        arr_city=_resolve_place_name(arr[2], arr[1], layover_cities),
        dep_datetime=dep[0],
        arr_datetime=arr[0],
        fare_class=cabin,
        aircraft=_clean_gf_aircraft(aircraft),
    )


def parse_google_flights(text, reference_date=None):
    """Parse a Google Flights paste into an Itinerary.

    Each Departure/Return slice becomes one Chunk. The price is taken from
    the last slice that states one: identical slices collapse to the same
    value, and differing slices resolve to the fully-selected combination.
    """
    reference = reference_date or date.today()
    layover_cities = _harvest_layover_cities(text)

    chunks = []
    currency, total_cost, trip_type = "$", None, None
    not_before = reference

    for block in _parse_gf_slices(text):
        base_date = _gf_slice_base_date(block, not_before)
        if base_date is None:
            continue
        not_before = base_date
        segments = _parse_gf_segments(block, base_date, layover_cities)
        if not segments:
            continue
        chunks.append(Chunk(segments=segments))

        symbol, amount = _gf_slice_price(block)
        if amount is not None:
            currency, total_cost = symbol, amount
        slice_trip_type = _gf_slice_trip_type(block)
        if slice_trip_type:
            trip_type = slice_trip_type

    return Itinerary(
        source="google_flights",
        chunks=chunks,
        total_cost=total_cost,
        currency=currency,
        trip_type=trip_type,
    )


def _render_itinerary_header_google_flights(it):
    """Header line: '- Google Flights itinerary: £1,387 round trip.'"""
    line = f"- {_SOURCE_LABEL['google_flights']} itinerary:"
    trailing = []
    if it.total_cost is not None:
        trailing.append(_fmt_money(it.total_cost, it.currency))
    if it.trip_type:
        trailing.append(it.trip_type)
    if not trailing:
        return line
    return f"{line} {' '.join(trailing)}."


def render_google_flights(it):
    """Render a Google Flights Itinerary as nested bullets."""
    lines = [_render_itinerary_header_google_flights(it)]
    for chunk in it.chunks:
        lines.append(_render_chunk_header_email(chunk))
        for seg in chunk.segments:
            lines.append(_render_segment_line_google_flights(seg))
    return "\n".join(lines)


# --- Email parser ---------------------------------------------------------

_EMAIL_FLIGHT_HEADER = re.compile(
    r"Flight (\d+) of (\d+)\s+UA(\d+)\s+Class:\s*(.+?)\s*\(([A-Z]+)\)"
)
_DATE_LINE = re.compile(
    r"[A-Za-z]{3},\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"
)
_TIME_LINE = re.compile(r"(\d{1,2}):(\d{2})\s*([APap][Mm])")
_CITY_LINE = re.compile(r"([^\t\n(]+?)\s*\(([A-Z]{3})\)")

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    # "May" is already in the dict (used for both full and abbreviated)
}


def _first_city_name(raw):
    """Extract city from 'Newark, NJ/New York, NY, US' style label
    (returns text up to first comma)."""
    return raw.split(",", 1)[0].strip()


def _to_24h(hour, minute, meridiem):
    meridiem = meridiem.upper()
    if meridiem == "AM":
        return (0 if hour == 12 else hour, minute)
    return (hour if hour == 12 else hour + 12, minute)


def _parse_email_segments(text):
    """Split an email body on 'Flight N of M' markers and parse each block.

    Block structure (tab-separated from HTML table copy-paste):
        Flight N of M UA<num>\tClass: United <name> (<code>)
        <Weekday>, <Mon DD, YYYY>\t<Weekday>, <Mon DD, YYYY>
        HH:MM AM/PM\tHH:MM AM/PM
        <DepCity, ..., Country (IATA)>\t<ArrCity, ..., Country (IATA)>
    """
    headers = list(_EMAIL_FLIGHT_HEADER.finditer(text))
    if not headers:
        return []

    segments = []
    for idx, m in enumerate(headers):
        start = m.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[start:end]

        dates = _DATE_LINE.findall(body)
        times = _TIME_LINE.findall(body)
        cities = _CITY_LINE.findall(body)
        if len(dates) < 2 or len(times) < 2 or len(cities) < 2:
            # Skip malformed block; don't raise — best-effort parity with the
            # existing reservation-UI parser.
            continue

        dep_month, dep_day, dep_year = dates[0]
        arr_month, arr_day, arr_year = dates[1]
        dep_h, dep_m, dep_mer = times[0]
        arr_h, arr_m, arr_mer = times[1]
        dep_city_raw, dep_iata = cities[0]
        arr_city_raw, arr_iata = cities[1]

        dep_hh, dep_mm = _to_24h(int(dep_h), int(dep_m), dep_mer)
        arr_hh, arr_mm = _to_24h(int(arr_h), int(arr_m), arr_mer)

        flight_num = m.group(3)
        class_name = m.group(4).strip()
        class_code = m.group(5)
        # Strip leading "United " for compactness
        if class_name.lower().startswith("united "):
            class_name = class_name[len("United "):]
        fare_class = f"{class_name} {class_code}"

        segments.append(Segment(
            flight_number=flight_num,
            dep_airport=dep_iata,
            dep_city=_first_city_name(dep_city_raw),
            arr_airport=arr_iata,
            arr_city=_first_city_name(arr_city_raw),
            dep_datetime=datetime(
                int(dep_year), _MONTHS[dep_month], int(dep_day), dep_hh, dep_mm,
            ),
            arr_datetime=datetime(
                int(arr_year), _MONTHS[arr_month], int(arr_day), arr_hh, arr_mm,
            ),
            fare_class=fare_class,
        ))
    return segments


_SEAT_PAIR = re.compile(r"([A-Z]{3})-([A-Z]{3})\s+([0-9]{1,3}[A-Z])")


def _attach_seats_from_traveler_details(text, segments):
    """Parse seat assignments from the Traveler Details block and attach by
    airport pair. Mutates segments in place."""
    start = text.find("Traveler Details")
    if start < 0:
        return
    end_candidates = [
        text.find("Purchase Summary", start),
        text.find("Additional Purchase Summary", start),
        text.find("Fare Rules", start),
    ]
    end_candidates = [c for c in end_candidates if c > 0]
    end = min(end_candidates) if end_candidates else len(text)
    region = text[start:end]

    seats_by_pair = {}
    for match in _SEAT_PAIR.finditer(region):
        dep, arr, seat = match.groups()
        seats_by_pair.setdefault((dep, arr), seat)

    for seg in segments:
        seg.seat = seats_by_pair.get((seg.dep_airport, seg.arr_airport))


_CONF_NUMBER = re.compile(r"Confirmation Number:\s*\n\s*([A-Z0-9]{6})")
_ETICKET = re.compile(r"eTicket number:\s*([0-9]+)")
_TOTAL_LINE = re.compile(r"^Total:\s+([\d,]+\.\d{2})\s*USD", re.MULTILINE)
_ACCRUAL_TOTALS = re.compile(
    r"MileagePlus accrual totals:\s+([\d,]+)\s+([\d,]+)\s+(\d+)"
)


def _decimal_or_none(s):
    if s is None:
        return None
    return Decimal(s.replace(",", ""))


def _int_or_none(s):
    if s is None:
        return None
    return int(s.replace(",", ""))


def parse_email(text):
    """Parse a United eTicket email body into an Itinerary."""
    segments = _parse_email_segments(text)
    _attach_seats_from_traveler_details(text, segments)
    chunks = group_into_chunks(segments)

    conf_m = _CONF_NUMBER.search(text)
    etk_m = _ETICKET.search(text)
    totals = _TOTAL_LINE.findall(text)
    accrual_m = _ACCRUAL_TOTALS.search(text)

    total_cost = _decimal_or_none(totals[0]) if totals else None
    upgrade_fees = None
    if len(totals) > 1:
        upgrade_fees = sum(
            (_decimal_or_none(t) for t in totals[1:]), start=Decimal("0")
        )

    return Itinerary(
        source="email",
        chunks=chunks,
        total_cost=total_cost,
        confirmation_number=conf_m.group(1) if conf_m else None,
        eticket_number=etk_m.group(1) if etk_m else None,
        upgrade_fees=upgrade_fees,
        accrual_award_miles=_int_or_none(accrual_m.group(1)) if accrual_m else None,
        accrual_pqp=_int_or_none(accrual_m.group(2)) if accrual_m else None,
        accrual_pqf=_int_or_none(accrual_m.group(3)) if accrual_m else None,
    )


# --- Email renderer -------------------------------------------------------

_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_SHORT = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_time_12h(dt):
    """Format time as '10:25 am' / '4:35 pm' / '12:15 pm' (no leading zero on hour)."""
    hour = dt.hour % 12 or 12
    meridiem = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt.minute:02d} {meridiem}"


def _fmt_money(amount, symbol="$"):
    """Format as '$2,565' — whole currency units, rounded half-up."""
    whole = Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{symbol}{whole:,}"


def _render_segment_line(seg, extras):
    """Render one segment line. `extras` become the parenthetical suffix."""
    dep_weekday = _WEEKDAY_SHORT[seg.dep_datetime.weekday()]
    dep_month = _MONTH_SHORT[seg.dep_datetime.month]
    dep_time = _fmt_time_12h(seg.dep_datetime)
    arr_time = _fmt_time_12h(seg.arr_datetime)

    arr_prefix = ""
    if seg.arr_datetime.date() != seg.dep_datetime.date():
        arr_prefix = f" {_WEEKDAY_SHORT[seg.arr_datetime.weekday()]}"

    extra_str = f" ({', '.join(extras)})" if extras else ""
    airline = seg.airline or "UA"

    return (
        f"    - {seg.dep_airport} > {seg.arr_airport} "
        f"{airline} {seg.flight_number}: "
        f"dep {seg.dep_airport} {dep_weekday} {dep_month} "
        f"{seg.dep_datetime.day}, {dep_time}, "
        f"arr {seg.arr_airport}{arr_prefix} {arr_time}{extra_str}."
    )


def _render_segment_line_email(seg):
    extras = []
    if seg.fare_class:
        extras.append(seg.fare_class)
    if seg.seat:
        extras.append(f"seat {seg.seat}")
    return _render_segment_line(seg, extras)


def _render_segment_line_google_flights(seg):
    extras = [value for value in (seg.fare_class, seg.aircraft) if value]
    return _render_segment_line(seg, extras)


def _render_chunk_header_email(chunk):
    first = chunk.segments[0]
    last = chunk.segments[-1]
    via_parts = [
        f"{seg.arr_city or seg.arr_airport} ({seg.arr_airport})"
        for seg in chunk.segments[:-1]
    ]
    via_str = f" (via {', '.join(via_parts)})" if via_parts else ""
    return (
        f"  - {first.dep_city or first.dep_airport} ({first.dep_airport}) "
        f"to {last.arr_city or last.arr_airport} ({last.arr_airport}){via_str}:"
    )


def _render_itinerary_header_email(it):
    parts = [f"- {_SOURCE_LABEL[it.source]} itinerary"]
    if it.confirmation_number:
        parts.append(f" {it.confirmation_number}")
    parts.append(":")

    trailing = []
    if it.total_cost is not None:
        cost_piece = _fmt_money(it.total_cost)
        if it.upgrade_fees:
            cost_piece += f" + {_fmt_money(it.upgrade_fees)} upgrades"
        trailing.append(cost_piece)
    if it.eticket_number:
        trailing.append(f"(eTicket {it.eticket_number})")

    line = "".join(parts)
    if trailing:
        line += " " + " ".join(trailing)
        if not line.endswith("."):
            line += "."

    if it.accrual_award_miles is not None:
        line += (
            f" Accrual: {it.accrual_award_miles:,} miles "
            f"/ {it.accrual_pqp:,} PQP / {it.accrual_pqf} PQF."
        )

    return line


def render_email(it):
    lines = [_render_itinerary_header_email(it)]
    for chunk in it.chunks:
        lines.append(_render_chunk_header_email(chunk))
        for seg in chunk.segments:
            lines.append(_render_segment_line_email(seg))
    return "\n".join(lines)


def _clean_duration(dur_str):
    """Clean a duration string like '23h 15m23 hours15 minutes' to '23h15m'."""
    time_match = re.search(r'^(\d+h(?: \d+m)?)', dur_str)
    if time_match:
        return time_match.group(1).replace(' ', '')
    return dur_str.replace(' ', '')


def _extract_layover_duration(text):
    """Extract layover duration from text between connections.

    Layover durations appear as bare 'Duration' (no colon) followed by time,
    e.g. 'Duration\\n10h 51m...' or 'Duration10 hours51 minutes'.
    """
    # "Xh Ym" format
    m = re.search(r'(\d+)h\s*(\d+)m', text)
    if m:
        return f"{m.group(1)}h{m.group(2)}m"
    # "X hoursY minutes" format (PopClip, possibly uppercase)
    m = re.search(r'(\d+)\s*hours?\s*(\d+)\s*minutes?', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}h{m.group(2)}m"
    # Hours only
    m = re.search(r'(\d+)\s*h(?:ours?)?', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}h"
    return None


def _split_sections(text):
    """Split text into flight sections by 'Flight X of Y' markers."""
    section_starts = list(re.finditer(r'Flight (\d+) of (\d+)', text))
    if not section_starts:
        return []
    sections = []
    for idx, match in enumerate(section_starts):
        start = match.start()
        end = section_starts[idx + 1].start() if idx + 1 < len(section_starts) else len(text)
        sections.append(text[start:end])
    return sections


def _parse_connections(section, conn_dt_pattern):
    """Parse connection subsections within a flight section.

    Returns (connections, layovers) where connections is a list of dicts with
    dep_airport, arr_airport, weekday, month, day, dep_time, arr_time;
    and layovers is a list of duration strings between consecutive connections.
    """
    route_pattern = r'([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'
    conn_starts = list(re.finditer(r'Connection (\d+) of (\d+)', section))
    if not conn_starts:
        return [], []

    connections = []
    layovers = []

    for i, conn_match in enumerate(conn_starts):
        conn_start = conn_match.start()
        conn_end = conn_starts[i + 1].start() if i + 1 < len(conn_starts) else len(section)
        conn_text = section[conn_start:conn_end]

        route_m = re.search(route_pattern, conn_text)
        dt_m = re.search(conn_dt_pattern, conn_text)

        if route_m and dt_m:
            connections.append({
                'dep_airport': route_m.group(2),
                'arr_airport': route_m.group(4),
                'weekday': dt_m.group(1),
                'month': dt_m.group(2),
                'day': dt_m.group(3),
                'dep_time': dt_m.group(4),
                'arr_time': dt_m.group(5),
            })

        # Extract layover duration: text after Aircraft type up to next Connection
        if i + 1 < len(conn_starts):
            aircraft_end = conn_text.rfind('Aircraft type:')
            if aircraft_end >= 0:
                gap_text = conn_text[aircraft_end:]
            else:
                gap_text = conn_text[len(conn_text) // 2:]
            layover = _extract_layover_duration(gap_text)
            if layover:
                layovers.append(layover)

    return connections, layovers


def _build_flight_line(route_str, flight_num, middle, stop_type, duration,
                       aircraft, layovers=None):
    """Build the formatted output line for a flight."""
    # Duration + aircraft info
    dur_str = duration
    if dur_str and layovers:
        layover_total = " + ".join(layovers) if len(layovers) > 1 else layovers[0]
        dur_str = f"{dur_str} incl {layover_total} layover"

    extra = ""
    if not dur_str and not aircraft:
        extra = "dur/aircraft: ???"
    elif not dur_str:
        extra = f"dur: ???, {aircraft}"
    elif not aircraft:
        extra = f"dur: {dur_str}"
    else:
        extra = f"{dur_str}, {aircraft}"

    stop_fmt = stop_type.lower() if stop_type != "???" else "???"
    return f"  - {route_str} UA {flight_num}: {middle} ({stop_fmt}, {extra})."


def parse_popclip_format(text):
    """Parse the PopClip format (• separators, full weekday names)."""

    output = []
    sections = _split_sections(text)
    if not sections:
        return output

    route_pattern = r'([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'
    weekdays = r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
    datetime_pattern = (
        weekdays + r', ([A-Za-z]+) (\d+)'
        r' • (\d{1,2}:\d{2} [ap]m) to (\d{1,2}:\d{2} [ap]m)'
        r' • (Nonstop|\d+ stops?)'
    )
    # Connection datetimes don't have stop type
    conn_dt_pattern = (
        weekdays + r', ([A-Za-z]+) (\d+)'
        r' • (\d{1,2}:\d{2} [ap]m) to (\d{1,2}:\d{2} [ap]m)'
    )

    for section in sections:
        route_match = re.search(route_pattern, section)
        if not route_match:
            continue
        dep_city, dep_airport, arr_city, arr_airport = route_match.groups()

        has_connections = bool(re.search(r'Connection \d+ of \d+', section))

        # Extract flight numbers and aircraft types
        flight_nums = [m.group(1) for m in re.finditer(r'Flight Number: UA (\d+)', section)]
        aircrafts = [m.group(1).strip() for m in re.finditer(
            r'Aircraft type: (.+?)(?=Duration|Connection|Hide|Carbon|Emission|\n|$)',
            section, re.IGNORECASE
        )]

        if has_connections:
            flight_num = "/".join(flight_nums) if flight_nums else None
            aircraft = "/".join(aircrafts) if aircrafts else None
        else:
            flight_num = flight_nums[0] if flight_nums else None
            aircraft = aircrafts[0] if aircrafts else None

        # Overall duration (before any Connection)
        connection_pos = re.search(r'Connection \d+ of \d+', section)
        pre_connection = section[:connection_pos.start()] if connection_pos else section
        dur_match = re.search(r'Duration: (\d+) hours?(\d*) minutes?', pre_connection)
        if dur_match:
            hours, minutes = dur_match.groups()
            duration = f"{hours}h"
            if minutes:
                duration += f"{minutes}m"
        else:
            duration = None

        if not flight_num:
            output.append(f"  - ERROR: Missing flight number for segment {dep_airport} > {arr_airport}")
            continue

        # Parse connections for detailed layover info
        connections, layovers = [], []
        if has_connections:
            connections, layovers = _parse_connections(section, conn_dt_pattern)

        if connections and len(connections) > 1:
            # Build route with intermediate airports
            airports = [connections[0]['dep_airport']]
            for c in connections:
                airports.append(c['arr_airport'])
            route_str = " > ".join(airports)

            # Build detailed timing
            parts = []
            for i, c in enumerate(connections):
                parts.append(f"dep {c['dep_airport']} {c['weekday'][:3]} {c['month'][:3]} {c['day']}, {c['dep_time']}")
                parts.append(f"arr {c['arr_airport']} {c['arr_time']}")
                if i < len(layovers):
                    parts.append(f"layover {layovers[i]}")
            middle = ", ".join(parts)

            # Get stop type from top-level datetime
            dt_match = re.search(datetime_pattern, section)
            stop_type = dt_match.group(6) if dt_match else "???"
        else:
            # Nonstop flight
            route_str = f"{dep_airport} > {arr_airport}"
            dt_match = re.search(datetime_pattern, section)
            if dt_match:
                weekday, month, day, dep_time, arr_time, stop_type = dt_match.groups()

                idx_after = dt_match.end()
                following_text = section[idx_after:min(idx_after + 400, len(section))]
                arr_date_note = ""
                if re.search(r'date change', following_text, re.IGNORECASE):
                    weekday_map = {
                        "Monday": "Tue", "Tuesday": "Wed", "Wednesday": "Thu",
                        "Thursday": "Fri", "Friday": "Sat", "Saturday": "Sun", "Sunday": "Mon"
                    }
                    arr_date_note = f" {weekday_map.get(weekday, 'next day')}"

                middle = f"dep {dep_airport} {weekday[:3]} {month[:3]} {day}, {dep_time}, arr {arr_airport}{arr_date_note} {arr_time}"
            else:
                stop_type = "???"
                middle = f"dep {dep_airport} ???, arr {arr_airport} ???"

        flight_line = _build_flight_line(route_str, flight_num, middle,
                                         stop_type, duration, aircraft, layovers)
        output.append(flight_line)

    return output


def parse_original_format(text):
    """Parse the original markdown/plain text format."""

    output = []
    sections = _split_sections(text)
    if not sections:
        return output

    route_pattern = r'(?:###\s+)?([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'
    # Use backreference \2 for repeated day to avoid ambiguity (e.g. "May 312:50 PM")
    datetime_pattern = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), ([A-Za-z]+) \2((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)(Nonstop|\d+ stop(?:over|s)?)'
    # Connection datetimes: same but no stop type, no backreference needed
    conn_dt_pattern = r'([A-Za-z]{3}) (\d{1,2})[A-Za-z]+, [A-Za-z]+ \2((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)'

    for section in sections:
        route_match = re.search(route_pattern, section)
        if not route_match:
            continue
        dep_city, dep_airport, arr_city, arr_airport = route_match.groups()

        has_connections = bool(re.search(r'Connection \d+ of \d+', section))

        # Extract flight numbers and aircraft types
        flight_nums = [m.group(1) for m in re.finditer(r'Flight Number: UA (\d+)', section)]
        aircrafts = [m.group(1).strip() for m in re.finditer(r'Aircraft type: ([^\n]+)', section)]
        aircrafts = [re.sub(r'\s*Carbon.*$', '', a) for a in aircrafts]

        if has_connections:
            flight_num = "/".join(flight_nums) if flight_nums else None
            aircraft = "/".join(aircrafts) if aircrafts else None
        else:
            flight_num = flight_nums[0] if flight_nums else None
            aircraft = aircrafts[0] if aircrafts else None

        # Overall duration (before any Connection marker)
        connection_pos = re.search(r'Connection \d+ of \d+', section)
        pre_connection = section[:connection_pos.start()] if connection_pos else section
        dur_match = re.search(r'Duration: ([^,\n]+)', pre_connection)
        duration = _clean_duration(dur_match.group(1).strip()) if dur_match else None

        if not flight_num:
            output.append(f"  - ERROR: Missing flight number for segment {dep_airport} > {arr_airport}")
            continue

        # Parse connections for detailed layover info
        connections, layovers = [], []
        if has_connections:
            # Connection datetime pattern: groups are (month, day, dep_time, arr_time)
            # We need (weekday, month, day, dep_time, arr_time) for _parse_connections
            # Use a custom pattern that extracts weekday too
            orig_conn_dt = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), [A-Za-z]+ \2((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)'
            conn_starts = list(re.finditer(r'Connection (\d+) of (\d+)', section))
            conn_route_pattern = r'([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'

            for i, conn_match in enumerate(conn_starts):
                conn_start = conn_match.start()
                conn_end = conn_starts[i + 1].start() if i + 1 < len(conn_starts) else len(section)
                conn_text = section[conn_start:conn_end]

                route_m = re.search(conn_route_pattern, conn_text)
                dt_m = re.search(orig_conn_dt, conn_text)

                if route_m and dt_m:
                    month_c, day_c, weekday_stuff, dep_time_c, arr_time_c = dt_m.groups()
                    wd_m = re.search(r'^([A-Za-z]{3})', weekday_stuff)
                    weekday_c = wd_m.group(1) if wd_m else "???"
                    connections.append({
                        'dep_airport': route_m.group(2),
                        'arr_airport': route_m.group(4),
                        'weekday': weekday_c,
                        'month': month_c,
                        'day': day_c,
                        'dep_time': dep_time_c.strip().lower(),
                        'arr_time': arr_time_c.strip().lower(),
                    })

                # Extract layover duration between this connection and next
                if i + 1 < len(conn_starts):
                    aircraft_end = conn_text.rfind('Aircraft type:')
                    gap_text = conn_text[aircraft_end:] if aircraft_end >= 0 else conn_text[len(conn_text) // 2:]
                    layover = _extract_layover_duration(gap_text)
                    if layover:
                        layovers.append(layover)

        if connections and len(connections) > 1:
            # Build route with intermediate airports
            airports = [connections[0]['dep_airport']]
            for c in connections:
                airports.append(c['arr_airport'])
            route_str = " > ".join(airports)

            # Build detailed timing
            parts = []
            for i, c in enumerate(connections):
                parts.append(f"dep {c['dep_airport']} {c['weekday']} {c['month']} {c['day']}, {c['dep_time']}")
                parts.append(f"arr {c['arr_airport']} {c['arr_time']}")
                if i < len(layovers):
                    parts.append(f"layover {layovers[i]}")
            middle = ", ".join(parts)

            # Get stop type from top-level datetime
            dt_match = re.search(datetime_pattern, section)
            stop_type = dt_match.group(7) if dt_match else "???"
        else:
            # Nonstop flight
            route_str = f"{dep_airport} > {arr_airport}"
            dt_match = re.search(datetime_pattern, section)
            if dt_match:
                month, day, weekday_and_more, month_full, dep_time, arr_time, stop_type = dt_match.groups()
                weekday_match = re.search(r'^([A-Za-z]{3})', weekday_and_more)
                weekday = weekday_match.group(1) if weekday_match else "???"

                idx_after = dt_match.end()
                next_flight = re.search(r'Flight \d+ of \d+', section[idx_after:])
                search_end = idx_after + next_flight.start() if next_flight else min(idx_after + 400, len(section))
                following_text = section[idx_after:search_end]
                arr_date_note = ""
                if re.search(r'involves a date change', following_text, re.IGNORECASE):
                    weekday_map = {
                        "Mon": "Tue", "Tue": "Wed", "Wed": "Thu",
                        "Thu": "Fri", "Fri": "Sat", "Sat": "Sun", "Sun": "Mon"
                    }
                    arr_date_note = f" {weekday_map.get(weekday, 'next day')}"

                dep_time_fmt = dep_time.strip().lower()
                arr_time_fmt = arr_time.strip().lower()
                middle = f"dep {dep_airport} {weekday} {month} {day}, {dep_time_fmt}, arr {arr_airport}{arr_date_note} {arr_time_fmt}"
            else:
                stop_type = "???"
                middle = f"dep {dep_airport} ???, arr {arr_airport} ???"

        flight_line = _build_flight_line(route_str, flight_num, middle,
                                         stop_type, duration, aircraft, layovers)
        output.append(flight_line)

    return output


def parse_united_itinerary(text, reference_date=None):
    """Convert an itinerary to a terse summary.

    Handles four input sources:
    - Google Flights web UI pastes (via parse_google_flights)
    - United eTicket/Receipt emails (via parse_email + render_email)
    - Reservation-UI text in PopClip format (bullet separators)
    - Reservation-UI text in original markdown format

    `reference_date` resolves the year of Google Flights dates, which omit
    it. Defaults to today; tests pin it so fixtures stay deterministic.
    """

    fmt = detect_format(text)

    if fmt == "google_flights":
        itinerary = parse_google_flights(text, reference_date=reference_date)
        if not itinerary.chunks:
            return ""
        return render_google_flights(itinerary)

    if fmt == "email":
        itinerary = parse_email(text)
        if not itinerary.chunks:
            return ""
        return render_email(itinerary)

    # Detect reservation-UI variant: PopClip format uses " • " separators
    if " • " in text:
        output = parse_popclip_format(text)
    else:
        output = parse_original_format(text)

    # If first parser found nothing, try the other
    if not output:
        if " • " in text:
            output = parse_original_format(text)
        else:
            output = parse_popclip_format(text)

    # Match cost and upgrade info
    cost_match = re.search(r'Total due\s*\$?([\d,]+\.\d{2})', text)
    miles_match = re.search(r'([\d,]+)\s*miles', text)
    plus_points_match = re.search(r'([\d,]+)\s*PlusPoints', text)

    cost_parts = []
    if cost_match:
        raw = cost_match.group(1).replace(',', '')
        cost_parts.append(_fmt_money(Decimal(raw)))
    if miles_match:
        miles_int = int(miles_match.group(1).replace(',', ''))
        cost_parts.append(f"{miles_int:,} miles")
    if plus_points_match:
        points_int = int(plus_points_match.group(1).replace(',', ''))
        cost_parts.append(f"{points_int:,} PlusPoints")

    # Add Itinerary header at the top with cost info
    if output:
        header = f"- {_SOURCE_LABEL['reservation_ui']} itinerary:"
        if cost_parts:
            header += " " + " + ".join(cost_parts)
        output.insert(0, header)

    return "\n".join(output)


def _get_input():
    """Return (text, from_clipboard). Sources in priority order:
    1. POPCLIP_TEXT env var (PopClip invocation)
    2. argv[1] file path (CLI file mode)
    3. stdin if piped
    4. pbpaste (macOS clipboard fallback)
    """
    import sys

    popclip = os.environ.get("POPCLIP_TEXT")
    if popclip:
        return popclip, False

    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                return f.read(), False
        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found", file=sys.stderr)
            sys.exit(1)

    if not sys.stdin.isatty():
        return sys.stdin.read(), False

    import subprocess
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, check=True
        )
        return result.stdout, True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: could not read clipboard", file=sys.stderr)
        sys.exit(1)


def _output_result(text, to_clipboard):
    import sys
    import subprocess

    if to_clipboard:
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: could not write clipboard", file=sys.stderr)
            sys.exit(1)
    else:
        print(text)


def main():
    import sys
    text, from_clipboard = _get_input()
    if not text.strip():
        print("Error: no input provided", file=sys.stderr)
        sys.exit(1)
    summary = parse_united_itinerary(text)
    if not summary:
        print("No valid United itinerary found.", file=sys.stderr)
        sys.exit(1)
    _output_result(summary, from_clipboard)


if __name__ == "__main__":
    main()
