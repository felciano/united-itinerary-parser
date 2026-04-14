#!/usr/bin/env python3
"""PopClip extension to parse United Airlines itineraries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
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


@dataclass
class Chunk:
    segments: list
    total_duration: Optional[timedelta] = None


@dataclass
class Itinerary:
    source: str  # "reservation_ui" | "email"
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


CHUNK_GAP_THRESHOLD = timedelta(hours=24)


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
    """Classify the input text as 'email', 'reservation_ui', or 'unknown'.

    Email signatures: both 'Thank you for choosing United' and
    'Confirmation Number:' appear (the combination rarely occurs
    coincidentally in reservation-UI text).

    Reservation-UI signatures: any of 'Flight selection list',
    'Aircraft type:', or 'Duration:' appears.

    If both match, email wins (more specific). If neither matches,
    returns 'unknown'.
    """
    is_email = (
        "Thank you for choosing United" in text
        and "Confirmation Number:" in text
    )
    is_reservation_ui = (
        "Flight selection list" in text
        or "Aircraft type:" in text
        or "Duration:" in text
    )
    if is_email:
        return "email"
    if is_reservation_ui:
        return "reservation_ui"
    return "unknown"


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


def parse_united_itinerary(text):
    """Convert a United itinerary to a terse summary. Supports both formats."""

    # Detect format: PopClip format uses " • " separators
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
        cost_parts.append(f"${cost_match.group(1)}")
    if miles_match:
        miles_int = int(miles_match.group(1).replace(',', ''))
        cost_parts.append(f"{miles_int:,} miles")
    if plus_points_match:
        points_int = int(plus_points_match.group(1).replace(',', ''))
        cost_parts.append(f"{points_int:,} PlusPoints")

    # Add Itinerary header at the top with cost info
    if output:
        header = "- Itinerary:"
        if cost_parts:
            header += " " + " + ".join(cost_parts)
        output.insert(0, header)

    return "\n".join(output)


if __name__ == "__main__":
    text = os.environ.get("POPCLIP_TEXT", "")
    if text:
        result = parse_united_itinerary(text)
        if result:
            print(result)
