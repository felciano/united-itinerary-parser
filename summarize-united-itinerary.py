#!/usr/bin/env python3

import re
import sys
import subprocess
import os


def parse_united_itinerary(text):
    """Convert a United itinerary to a terse summary."""
    
    # Find route headers first (### is optional - may not be present in pasted text)
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
        # Extract just the time part from strings like "11h11 hours" or "5h 40m5 hours40 minutes"
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
        # Find the next duration after this route
        while duration_idx < len(duration_matches) and duration_matches[duration_idx][0] < route_pos:
            duration_idx += 1
        
        if duration_idx < len(duration_matches):
            # Check if this duration is before the next route
            next_route_pos = route_matches[route_idx + 1].start() if route_idx + 1 < len(route_matches) else float('inf')
            if duration_matches[duration_idx][0] < next_route_pos:
                route_durations[route_idx] = duration_matches[duration_idx][1]
                duration_idx += 1
    
    # Find date/time patterns for each route
    # Pattern: "Aug 21Thursday, August 2112:20 PM to 3:20 PMNonstop"
    # Time must be 1-12 (not 0) to prevent greedy matching of day + first time digit
    datetime_pattern = r'([A-Za-z]{3}) (\d{1,2})([A-Za-z]+), ([A-Za-z]+) (\d{1,2})((?:1[0-2]|[1-9]):\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)(Nonstop|\d+ stop(?:over)?)'
    datetime_matches = list(re.finditer(datetime_pattern, text))
    
    output = []
    
    # Process each flight
    for i, (dep_city, dep_airport, arr_city, arr_airport) in enumerate(routes):
        # Get corresponding flight details
        flight_num = flight_nums[i] if i < len(flight_nums) else None
        duration = route_durations[i]  # This is already None if no duration found
        aircraft = aircrafts[i] if i < len(aircrafts) else None
        
        if not flight_num:
            output.append(f"ERROR: Missing flight number for segment {dep_airport} > {arr_airport}")
            continue
            
        # Get datetime info
        if i < len(datetime_matches):
            dt_match = datetime_matches[i]
            month, day, weekday_and_more, month_full, day_full, dep_time, arr_time, stop_type = dt_match.groups()
            
            # Extract weekday from the combined string
            weekday_match = re.search(r'^([A-Za-z]{3})', weekday_and_more)
            weekday = weekday_match.group(1) if weekday_match else "???"
            
            # Check for date change in following text - but only until the next flight section
            idx_after = dt_match.end()
            # Find the next "Flight" section or end of text
            next_flight_match = re.search(r'Flight \d+ of \d+', text[idx_after:])
            if next_flight_match:
                search_end = idx_after + next_flight_match.start()
            else:
                search_end = idx_after + 400
            following_text = text[idx_after:search_end]
            date_change_match = re.search(r'involves a date change', following_text, re.IGNORECASE)
            
            # Calculate arrival date note
            arr_date_note = ""
            if date_change_match:
                # Map weekdays to next day
                weekday_map = {
                    "Mon": "Tue", "Tue": "Wed", "Wed": "Thu", 
                    "Thu": "Fri", "Fri": "Sat", "Sat": "Sun", "Sun": "Mon"
                }
                arr_date_note = f" {weekday_map.get(weekday, 'next day')}"
        else:
            month = day = weekday = dep_time = arr_time = stop_type = "???"
            arr_date_note = ""
        
        # Build extra info string
        extra = ""
        if not duration and not aircraft:
            extra = "dur/aircraft: ???"
        elif not duration:
            extra = f"dur: ???, {aircraft}"
        elif not aircraft:
            extra = f"dur: {duration}"
        else:
            extra = f"{duration}, {aircraft}"
        
        # Format time strings (convert to lowercase AM/PM)
        dep_time_formatted = dep_time.strip().lower() if dep_time != "???" else "???"
        arr_time_formatted = arr_time.strip().lower() if arr_time != "???" else "???"
        
        # Create flight line (indented under Itinerary header)
        flight_line = f"  - {dep_airport} > {arr_airport} UA {flight_num}: dep {dep_airport} {weekday} {month} {day}, {dep_time_formatted}, arr {arr_airport}{arr_date_note} {arr_time_formatted} ({stop_type.lower() if stop_type != '???' else '???'}, {extra})."
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
