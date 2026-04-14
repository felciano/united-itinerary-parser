#!/usr/bin/env python3

import re
import sys
import subprocess
import os


def _clean_duration(dur_str):
    """Clean a duration string like '23h 15m23 hours15 minutes' to '23h15m'."""
    time_match = re.search(r'^(\d+h(?: \d+m)?)', dur_str)
    if time_match:
        return time_match.group(1).replace(' ', '')
    return dur_str.replace(' ', '')


def _extract_layover_duration(text):
    """Extract layover duration from text between connections."""
    m = re.search(r'(\d+)h\s*(\d+)m', text)
    if m:
        return f"{m.group(1)}h{m.group(2)}m"
    m = re.search(r'(\d+)\s*hours?\s*(\d+)\s*minutes?', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}h{m.group(2)}m"
    m = re.search(r'(\d+)\s*h(?:ours?)?', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}h"
    return None


def _build_flight_line(route_str, flight_num, middle, stop_type, duration,
                       aircraft, layovers=None):
    """Build the formatted output line for a flight."""
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


def parse_united_itinerary(text):
    """Convert a United itinerary to a terse summary."""

    output = []

    # Split text into flight sections using "Flight X of Y" markers
    section_starts = list(re.finditer(r'Flight (\d+) of (\d+)', text))

    if not section_starts:
        return ""

    sections = []
    for idx, match in enumerate(section_starts):
        start = match.start()
        end = section_starts[idx + 1].start() if idx + 1 < len(section_starts) else len(text)
        sections.append(text[start:end])

    route_pattern = r'(?:###\s+)?([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'
    datetime_pattern = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), ([A-Za-z]+) \2((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)(Nonstop|\d+ stop(?:over|s)?)'
    conn_dt_pattern = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), [A-Za-z]+ \2((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)'

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
            conn_starts = list(re.finditer(r'Connection (\d+) of (\d+)', section))
            conn_route_pattern = r'([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})'

            for i, conn_match in enumerate(conn_starts):
                conn_start = conn_match.start()
                conn_end = conn_starts[i + 1].start() if i + 1 < len(conn_starts) else len(section)
                conn_text = section[conn_start:conn_end]

                route_m = re.search(conn_route_pattern, conn_text)
                dt_m = re.search(conn_dt_pattern, conn_text)

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

                if i + 1 < len(conn_starts):
                    aircraft_end = conn_text.rfind('Aircraft type:')
                    gap_text = conn_text[aircraft_end:] if aircraft_end >= 0 else conn_text[len(conn_text) // 2:]
                    layover = _extract_layover_duration(gap_text)
                    if layover:
                        layovers.append(layover)

        if connections and len(connections) > 1:
            airports = [connections[0]['dep_airport']]
            for c in connections:
                airports.append(c['arr_airport'])
            route_str = " > ".join(airports)

            parts = []
            for i, c in enumerate(connections):
                parts.append(f"dep {c['dep_airport']} {c['weekday']} {c['month']} {c['day']}, {c['dep_time']}")
                parts.append(f"arr {c['arr_airport']} {c['arr_time']}")
                if i < len(layovers):
                    parts.append(f"layover {layovers[i]}")
            middle = ", ".join(parts)

            dt_match = re.search(datetime_pattern, section)
            stop_type = dt_match.group(7) if dt_match else "???"
        else:
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
    
    # Match cost and upgrade info
    cost_match = re.search(r'Total due\s+\$([\d,]+\.\d{2})', text)
    miles_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+) miles', text)
    plus_points_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+) PlusPoints', text)
    
    cost_line = []
    if cost_match:
        cost_line.append(f"${cost_match.group(1)}")
    if miles_match:
        miles_int = int(miles_match.group(1).replace(',', ''))
        cost_line.append(f"{miles_int:,} miles")
    if plus_points_match:
        points_int = int(plus_points_match.group(1).replace(',', ''))
        cost_line.append(f"{points_int:,} PlusPoints")
    
    # Add Itinerary header at the top with cost info
    if output:
        header = "- Itinerary:"
        if cost_line:
            header += " " + " + ".join(cost_line)
        output.insert(0, header)

    return "\n".join(output)


def get_input():
    """Get input from stdin, file argument, or clipboard."""
    # Check if there's a file argument
    if len(sys.argv) > 1:
        filename = sys.argv[1]
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read(), False
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Check if there's input from stdin
    if not sys.stdin.isatty():
        return sys.stdin.read(), False
    
    # Fall back to clipboard
    try:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True, check=True)
        return result.stdout, True
    except subprocess.CalledProcessError:
        print("Error: Could not read from clipboard", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: pbpaste command not found (are you on macOS?)", file=sys.stderr)
        sys.exit(1)


def output_result(text, to_clipboard=False):
    """Output result to stdout or clipboard."""
    if to_clipboard:
        try:
            subprocess.run(['pbcopy'], input=text, text=True, check=True)
        except subprocess.CalledProcessError:
            print("Error: Could not write to clipboard", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: pbcopy command not found (are you on macOS?)", file=sys.stderr)
            sys.exit(1)
    else:
        print(text)


def main():
    """Main function."""
    input_text, from_clipboard = get_input()
    
    if not input_text.strip():
        print("Error: No input provided", file=sys.stderr)
        sys.exit(1)
    
    summary = parse_united_itinerary(input_text)
    
    if not summary:
        print("No valid United itinerary found.", file=sys.stderr)
        sys.exit(1)
    
    output_result(summary, from_clipboard)


if __name__ == "__main__":
    main()
