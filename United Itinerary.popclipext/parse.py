#!/usr/bin/env python3
"""PopClip extension to parse United Airlines itineraries."""

import os
import re


def parse_popclip_format(text):
    """Parse the PopClip format (• separators, full weekday names)."""

    output = []

    # Pattern for PopClip format (all on one line with • separators):
    # "San Francisco SFO to London LHRWednesday, February 11 • 12:50 pm to 7:25 am • Nonstop"
    flight_pattern = re.compile(
        r'([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'  # Route
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Za-z]+) (\d+)'  # Day, Month, Date
        r' • (\d{1,2}:\d{2} [ap]m) to (\d{1,2}:\d{2} [ap]m)'  # Times
        r' • (Nonstop|\d+ stops?)'  # Stops
        r'.*?'  # Skip date change notice if present
        r'Duration: (\d+) hours?(\d*) minutes?'  # Duration
        r'.*?'
        r'Flight Number: UA (\d+)'  # Flight number
        r'Aircraft type: ([^C]+?)(?:Carbon|$)'  # Aircraft (stop before Carbon)
    )

    for match in flight_pattern.finditer(text):
        dep_city, dep_airport, arr_city, arr_airport = match.group(1, 2, 3, 4)
        weekday, month, day = match.group(5, 6, 7)
        dep_time, arr_time = match.group(8, 9)
        stop_type = match.group(10)
        hours, minutes = match.group(11, 12)
        flight_num = match.group(13)
        aircraft = match.group(14).strip()

        # Format duration
        duration = f"{hours}h"
        if minutes:
            duration += f"{minutes}m"

        # Check for date change
        flight_text = match.group(0)
        arr_date_note = ""
        if "date change" in flight_text.lower():
            weekday_map = {
                "Monday": "Tue", "Tuesday": "Wed", "Wednesday": "Thu",
                "Thursday": "Fri", "Friday": "Sat", "Saturday": "Sun", "Sunday": "Mon"
            }
            arr_date_note = f" {weekday_map.get(weekday, 'next day')}"

        # Abbreviate weekday and month
        weekday_abbr = weekday[:3]
        month_abbr = month[:3]

        flight_line = f"  - {dep_airport} > {arr_airport} UA {flight_num}: dep {dep_airport} {weekday_abbr} {month_abbr} {day}, {dep_time}, arr {arr_airport}{arr_date_note} {arr_time} ({stop_type.lower()}, {duration}, {aircraft})."
        output.append(flight_line)

    return output


def parse_original_format(text):
    """Parse the original markdown/plain text format."""

    output = []

    # Find route headers (### is optional)
    route_pattern = r'(?:###\s+)?([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'
    route_matches = list(re.finditer(route_pattern, text))
    routes = [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in route_matches]

    # Extract all flight numbers and aircraft types
    flight_nums = [m.group(1) for m in re.finditer(r'Flight Number: UA (\d+)', text)]
    aircrafts = [m.group(1) for m in re.finditer(r'Aircraft type: (.+)', text)]

    # Map durations to routes based on position in text
    duration_matches = []
    for m in re.finditer(r'Duration: ([^,\n]+)', text):
        dur = m.group(1).strip()
        time_match = re.search(r'^(\d+h(?: \d+m)?)', dur)
        if time_match:
            dur_clean = time_match.group(1).replace(' ', '')
        else:
            dur_clean = dur.replace(' ', '')
        duration_matches.append((m.start(), dur_clean))

    # Map durations to routes based on position
    route_durations = [None] * len(routes)
    duration_idx = 0

    for route_idx, route_match in enumerate(route_matches):
        route_pos = route_match.start()
        while duration_idx < len(duration_matches) and duration_matches[duration_idx][0] < route_pos:
            duration_idx += 1

        if duration_idx < len(duration_matches):
            next_route_pos = route_matches[route_idx + 1].start() if route_idx + 1 < len(route_matches) else float('inf')
            if duration_matches[duration_idx][0] < next_route_pos:
                route_durations[route_idx] = duration_matches[duration_idx][1]
                duration_idx += 1

    # Find date/time patterns
    # Time must be 1-12 (not 0) to prevent greedy matching
    datetime_pattern = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), ([A-Za-z]+) (\d{1,2})((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)(Nonstop|\d+ stop(?:over)?)'
    datetime_matches = list(re.finditer(datetime_pattern, text))

    # Process each flight
    for i, (dep_city, dep_airport, arr_city, arr_airport) in enumerate(routes):
        flight_num = flight_nums[i] if i < len(flight_nums) else None
        duration = route_durations[i]
        aircraft = aircrafts[i] if i < len(aircrafts) else None

        if not flight_num:
            output.append(f"  - ERROR: Missing flight number for segment {dep_airport} > {arr_airport}")
            continue

        if i < len(datetime_matches):
            dt_match = datetime_matches[i]
            month, day, weekday_and_more, month_full, day_full, dep_time, arr_time, stop_type = dt_match.groups()

            weekday_match = re.search(r'^([A-Za-z]{3})', weekday_and_more)
            weekday = weekday_match.group(1) if weekday_match else "???"

            idx_after = dt_match.end()
            next_flight_match = re.search(r'Flight \d+ of \d+', text[idx_after:])
            if next_flight_match:
                search_end = idx_after + next_flight_match.start()
            else:
                search_end = idx_after + 400
            following_text = text[idx_after:search_end]
            date_change_match = re.search(r'involves a date change', following_text, re.IGNORECASE)

            arr_date_note = ""
            if date_change_match:
                weekday_map = {
                    "Mon": "Tue", "Tue": "Wed", "Wed": "Thu",
                    "Thu": "Fri", "Fri": "Sat", "Sat": "Sun", "Sun": "Mon"
                }
                arr_date_note = f" {weekday_map.get(weekday, 'next day')}"
        else:
            month = day = weekday = dep_time = arr_time = stop_type = "???"
            arr_date_note = ""

        extra = ""
        if not duration and not aircraft:
            extra = "dur/aircraft: ???"
        elif not duration:
            extra = f"dur: ???, {aircraft}"
        elif not aircraft:
            extra = f"dur: {duration}"
        else:
            extra = f"{duration}, {aircraft}"

        dep_time_formatted = dep_time.strip().lower() if dep_time != "???" else "???"
        arr_time_formatted = arr_time.strip().lower() if arr_time != "???" else "???"

        flight_line = f"  - {dep_airport} > {arr_airport} UA {flight_num}: dep {dep_airport} {weekday} {month} {day}, {dep_time_formatted}, arr {arr_airport}{arr_date_note} {arr_time_formatted} ({stop_type.lower() if stop_type != '???' else '???'}, {extra})."
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
