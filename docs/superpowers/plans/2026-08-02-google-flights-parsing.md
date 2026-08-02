# Google Flights Itinerary Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the parser to recognize itineraries copied from the Google Flights web UI, label every rendered itinerary with its source, and drop decimals from all prices.

**Architecture:** Everything lives in `United Itinerary.popclipext/parse.py`. Google Flights input is parsed by anchoring on seven structural line shapes and ignoring everything else, producing the existing `Itinerary`/`Chunk`/`Segment` dataclasses. A new renderer reuses the email renderer's chunk header and a newly extracted shared segment-line core. `detect_format` gains a third branch.

**Tech Stack:** Python 3.9+, standard library only. `pytest` + `PyYAML` as dev-only dependencies. `uv` for environment management.

## Global Constraints

- `United Itinerary.popclipext/parse.py` MUST remain a **single file** with **only standard-library imports**. Other macOS utilities shell out to it as a bare `python3 parse.py` against the system interpreter. Never split it into modules; use section banners. Never add a runtime dependency.
- `pytest` and `PyYAML` stay in `[dependency-groups]` and are NEVER imported by `parse.py`.
- `summarize-united-itinerary.py` is a symlink to `parse.py`. Do not replace it with a regular file.
- Line length 88 characters maximum. Functions 30 lines maximum.
- Existing reservation-UI and email **segment and chunk lines** must stay byte-identical. Only the itinerary **header** line changes (source qualifier, price precision).
- All commits end with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- Run the full suite with `uv run pytest` from the repo root.

**Reference spec:** `docs/superpowers/specs/2026-08-02-google-flights-parsing-design.md`

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `United Itinerary.popclipext/parse.py` | All parsing and rendering | Modify |
| `tests/test_money_and_source.py` | Price formatting and source qualifier | Create |
| `tests/test_infer_year.py` | Year inference from weekday | Create |
| `tests/test_gf_anchors.py` | The five Google Flights regexes | Create |
| `tests/test_gf_place_names.py` | Three-tier place-name resolution | Create |
| `tests/test_gf_parse.py` | `parse_google_flights` structure | Create |
| `tests/test_gf_render.py` | `render_google_flights` output | Create |
| `tests/test_gf_end_to_end.py` | YAML fixture round-trip | Create |
| `tests/test_detect_format.py` | Add `google_flights` cases | Modify |
| `tests/test_reservation_ui_snapshot.py` | Unchanged (fixtures regenerate) | — |
| `tests/test_render_email.py` | Two inline expected strings | Modify |
| `test-cases/test-case-{1..6}.yaml` | Header line regenerates | Modify |
| `test-cases/test-case-email-*.yaml` | Header line regenerates | Modify |
| `test-cases/test-case-gf-*-input.txt` | Raw Google Flights pastes | Create (6) |
| `test-cases/test-case-gf-*.yaml` | Expected summaries | Create (6) |
| `README.md` | Document the third input format | Modify |

---

## Task 1: Decimal-free prices and source qualifier

Both changes touch the same header lines and the same ten assertions, so they land together to avoid regenerating fixtures twice.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (imports, `_fmt_money` at :299, `_render_itinerary_header_email` at :343, `parse_united_itinerary` at :776-791)
- Create: `tests/test_money_and_source.py`
- Modify: `test-cases/test-case-1.yaml`, `-2`, `-3`, `-4`, `-5`, `-6`
- Modify: `test-cases/test-case-email-NLY82V.yaml`, `test-case-email-FQZ1B5.yaml`
- Modify: `tests/test_render_email.py`

**Interfaces:**
- Produces: `_fmt_money(amount: Decimal, symbol: str = "$") -> str`; `_SOURCE_LABEL: dict[str, str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_money_and_source.py`:

```python
"""Price formatting and the source qualifier on itinerary headers."""
from __future__ import annotations

from decimal import Decimal

import parse as parser


def test_fmt_money_drops_decimals():
    assert parser._fmt_money(Decimal("2564.60")) == "$2,565"


def test_fmt_money_rounds_half_up():
    assert parser._fmt_money(Decimal("556.50")) == "$557"


def test_fmt_money_rounds_down_below_half():
    assert parser._fmt_money(Decimal("3248.25")) == "$3,248"


def test_fmt_money_whole_amount_unchanged():
    assert parser._fmt_money(Decimal("2740.00")) == "$2,740"


def test_fmt_money_honours_currency_symbol():
    assert parser._fmt_money(Decimal("1387"), "£") == "£1,387"


def test_source_labels():
    assert parser._SOURCE_LABEL["reservation_ui"] == "United.com"
    assert parser._SOURCE_LABEL["email"] == "United.com"
    assert parser._SOURCE_LABEL["google_flights"] == "Google Flights"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_money_and_source.py -v`
Expected: FAIL — `_fmt_money() takes 1 positional argument but 2 were given` on the symbol test, and `AttributeError: module 'parse' has no attribute '_SOURCE_LABEL'`.

- [ ] **Step 3: Widen the Decimal import**

In `parse.py` line 10, replace:

```python
from decimal import Decimal
```

with:

```python
from decimal import ROUND_HALF_UP, Decimal
```

- [ ] **Step 4: Add `_SOURCE_LABEL` below the `CHUNK_GAP_THRESHOLD` constant (:50)**

```python
_SOURCE_LABEL = {
    "reservation_ui": "United.com",
    "email": "United.com",
    "google_flights": "Google Flights",
}
```

- [ ] **Step 5: Replace `_fmt_money` (:299-301)**

```python
def _fmt_money(amount, symbol="$"):
    """Format as '$2,565' — whole currency units, rounded half-up."""
    whole = Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{symbol}{whole:,}"
```

- [ ] **Step 6: Run the money tests; expect PASS**

Run: `uv run pytest tests/test_money_and_source.py -v`
Expected: all 6 PASS.

- [ ] **Step 7: Add the qualifier to the email header (:344)**

In `_render_itinerary_header_email`, replace:

```python
    parts = ["- Itinerary"]
```

with:

```python
    parts = [f"- {_SOURCE_LABEL[it.source]} itinerary"]
```

- [ ] **Step 8: Add the qualifier and Decimal conversion to the reservation-UI header**

In `parse_united_itinerary`, replace lines 776-791:

```python
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
```

with:

```python
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
```

- [ ] **Step 9: Run the full suite to see exactly which fixtures drift**

Run: `uv run pytest -v`
Expected: FAIL on 8 tests — 6 reservation-UI snapshots and 2 `test_render_email` cases. Read each diff and confirm **only** the header line differs. If any segment or chunk line changed, stop: the shared renderer was altered by mistake.

- [ ] **Step 10: Update the two inline strings in `tests/test_render_email.py`**

Line 12, replace:

```python
- Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
```

with:

```python
- United.com itinerary NLY82V: $557 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
```

Line 17, replace:

```python
- Itinerary FQZ1B5: $2,564.60 + $1,100.00 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.
```

with:

```python
- United.com itinerary FQZ1B5: $2,565 + $1,100 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.
```

- [ ] **Step 11: Update the eight YAML fixture header lines**

Each file has exactly one `- Itinerary...` line inside `expected_summary`. Replace as follows, preserving the existing indentation:

| File | Old | New |
|---|---|---|
| `test-case-1.yaml:92` | `- Itinerary: $3,185.23 + 55,000 miles` | `- United.com itinerary: $3,185 + 55,000 miles` |
| `test-case-2.yaml:56` | `- Itinerary: $1,399.01 + 70 PlusPoints` | `- United.com itinerary: $1,399 + 70 PlusPoints` |
| `test-case-3.yaml:68` | `- Itinerary: $3,185.23 + 55,000 miles` | `- United.com itinerary: $3,185 + 55,000 miles` |
| `test-case-4.yaml:57` | `- Itinerary: $2,740.00` | `- United.com itinerary: $2,740` |
| `test-case-5.yaml:81` | `- Itinerary: $2,294.83 + 40,000 miles` | `- United.com itinerary: $2,295 + 40,000 miles` |
| `test-case-6.yaml:4` | `- Itinerary: $3,248.25 + 62,500 miles` | `- United.com itinerary: $3,248 + 62,500 miles` |

And the two email fixtures:

| File | Old | New |
|---|---|---|
| `test-case-email-NLY82V.yaml` | `- Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.` | `- United.com itinerary NLY82V: $557 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.` |
| `test-case-email-FQZ1B5.yaml` | `- Itinerary FQZ1B5: $2,564.60 + $1,100.00 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.` | `- United.com itinerary FQZ1B5: $2,565 + $1,100 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.` |

- [ ] **Step 12: Run the full suite; expect all PASS**

Run: `uv run pytest -v`
Expected: 38 passed (32 existing + 6 new).

- [ ] **Step 13: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/ test-cases/
git commit -m "feat: label itinerary source and drop price decimals

Every rendered header now leads with its source -- 'United.com
itinerary' or 'Google Flights itinerary' -- and prices render as whole
currency units rounded half-up, so \$2,564.60 becomes \$2,565.

_fmt_money takes a currency symbol so non-USD sources can reuse it.
Regenerates the ten assertions that pinned the old header; segment and
chunk lines are unchanged.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Data model deltas and the shared segment-line renderer

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (dataclasses at :14-47, `_render_segment_line_email` at :304)
- Create: `tests/test_gf_data_model.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Segment.airline: Optional[str]`; `Itinerary.currency: str`; `Itinerary.trip_type: Optional[str]`; `_render_segment_line(seg, extras: list[str]) -> str`; `_render_segment_line_google_flights(seg) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gf_data_model.py`:

```python
"""New model fields and the shared segment-line renderer."""
from __future__ import annotations

from datetime import datetime

import parse as parser


def _seg(**overrides):
    base = dict(
        flight_number="355",
        dep_airport="LHR", dep_city="Heathrow",
        arr_airport="GVA", arr_city="Geneva",
        dep_datetime=datetime(2026, 8, 26, 14, 25),
        arr_datetime=datetime(2026, 8, 26, 17, 5),
    )
    base.update(overrides)
    return parser.Segment(**base)


def test_segment_airline_defaults_to_none():
    assert _seg().airline is None


def test_itinerary_currency_and_trip_type_defaults():
    it = parser.Itinerary(source="google_flights")
    assert it.currency == "$"
    assert it.trip_type is None


def test_segment_line_falls_back_to_ua_when_airline_absent():
    line = parser._render_segment_line(_seg(), [])
    assert line.startswith("    - LHR > GVA UA 355:")


def test_segment_line_uses_airline_when_present():
    line = parser._render_segment_line(_seg(airline="LX"), [])
    assert line.startswith("    - LHR > GVA LX 355:")


def test_google_flights_extras_are_cabin_and_aircraft():
    seg = _seg(airline="LX", fare_class="Economy", aircraft="Airbus A220-300")
    line = parser._render_segment_line_google_flights(seg)
    assert line.endswith("(Economy, Airbus A220-300).")


def test_google_flights_extras_omit_missing_values():
    seg = _seg(airline="LX", fare_class="Economy")
    line = parser._render_segment_line_google_flights(seg)
    assert line.endswith("(Economy).")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gf_data_model.py -v`
Expected: FAIL — `Segment.__init__() got an unexpected keyword argument 'airline'` and `module 'parse' has no attribute '_render_segment_line'`.

- [ ] **Step 3: Add `airline` to `Segment` (:14-26)**

Append `airline` at the **end** of the field list, after `duration`. Do not
insert it near `flight_number` where it reads more naturally: `Segment` has
required fields followed by defaulted ones, and a defaulted field cannot
precede a required one. Appending also leaves any positional construction
working.

```python
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
```

- [ ] **Step 4: Add `currency` and `trip_type` to `Itinerary` (:35-47)**

Append at the end of the field list, after `accrual_pqf`:

```python
    currency: str = "$"
    trip_type: Optional[str] = None
```

- [ ] **Step 5: Extract the shared segment-line core**

Replace `_render_segment_line_email` (:304-326) with three functions:

```python
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
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: 44 passed. The email and reservation-UI fixtures must still pass — `seg.airline` is `None` for those, so `"UA"` is used and output is unchanged.

- [ ] **Step 7: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_gf_data_model.py
git commit -m "feat: add airline, currency and trip_type to the data model

Extracts _render_segment_line as a shared core so the email and Google
Flights renderers differ only in their parenthetical extras. The
hardcoded UA prefix becomes seg.airline or 'UA', which leaves existing
output byte-identical because those parsers never set it.

New fields are appended to the dataclasses so existing positional
construction keeps working.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Year inference from the weekday

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (imports, new section after `detect_format`)
- Create: `tests/test_infer_year.py`

**Interfaces:**
- Produces: `_infer_year(month: int, day: int, weekday: str, reference: date) -> int`; `_WEEKDAY_NUM: dict[str, int]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_infer_year.py`:

```python
"""Year inference for Google Flights dates, which carry no year."""
from __future__ import annotations

from datetime import date

import parse as parser

REF = date(2026, 8, 2)


def test_matches_weekday_in_current_year():
    # 2026-08-26 is a Wednesday
    assert parser._infer_year(8, 26, "Wed", REF) == 2026


def test_matches_weekday_later_in_current_year():
    # 2026-08-30 is a Sunday
    assert parser._infer_year(8, 30, "Sun", REF) == 2026


def test_rolls_into_next_year_when_date_already_passed():
    # 2027-01-03 is a Sunday; 2026-01-03 is before the reference
    assert parser._infer_year(1, 3, "Sun", REF) == 2027


def test_spans_an_eleven_year_gap():
    # Aug 26 is Wednesday in 2026, then not again until 2037
    assert parser._infer_year(8, 26, "Wed", date(2027, 1, 1)) == 2037


def test_unknown_weekday_falls_back_to_first_candidate():
    assert parser._infer_year(8, 26, "Xxx", REF) == 2026


def test_skips_feb_29_in_non_leap_years():
    # 2028-02-29 is a Tuesday; 2027 has no Feb 29
    assert parser._infer_year(2, 29, "Tue", date(2027, 1, 1)) == 2028
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_infer_year.py -v`
Expected: FAIL with `AttributeError: module 'parse' has no attribute '_infer_year'`.

- [ ] **Step 3: Widen the datetime import**

In `parse.py` line 9, replace:

```python
from datetime import datetime, timedelta
```

with:

```python
from datetime import date, datetime, timedelta
```

- [ ] **Step 4: Implement `_infer_year`**

Add below `detect_format` (after :108), under a new section banner:

```python
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
```

- [ ] **Step 5: Run tests; expect PASS**

Run: `uv run pytest tests/test_infer_year.py -v`
Expected: all 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_infer_year.py
git commit -m "feat: infer the year of a Google Flights date from its weekday

Google Flights prints 'Wed, Aug 26' with no year. Searching forward
from a reference date for the first month/day whose weekday agrees
recovers it, and self-validates as a side effect.

The window is 12 years, not the more obvious 7: a date returns to the
same weekday on an irregular cycle and Wed Aug 26 gaps from 2026 to
2037.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The five anchor regexes

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (Google Flights section)
- Create: `tests/test_gf_anchors.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_GF_SLICE_HEADER`, `_GF_SLICE_DATE`, `_GF_PRICE`, `_GF_TIME_AIRPORT`, `_GF_FLIGHT`, `_GF_LAYOVER` (compiled patterns); `_clean_gf_aircraft(raw: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gf_anchors.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gf_anchors.py -v`
Expected: FAIL with `AttributeError: module 'parse' has no attribute '_GF_TIME_AIRPORT'`.

- [ ] **Step 3: Implement the anchors**

Add below `_infer_year` in the Google Flights section:

```python
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
```

Two notes on why these are shaped this way. `_GF_FLIGHT` uses `.+?` rather
than `.*?` for the airline group so an airline whose name starts with a cabin
word (`First Air`) cannot have that word consumed as the cabin. The cabin
alternation lists `Premium economy` before `Economy` because Python's `|` is
first-match, not longest-match.

- [ ] **Step 4: Run tests; expect PASS**

Run: `uv run pytest tests/test_gf_anchors.py -v`
Expected: all 35 PASS (the parametrized cases expand to 35).

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_gf_anchors.py
git commit -m "feat: add the Google Flights line anchors

Six regexes cover every line that carries signal. Everything else --
legroom, Wi-Fi, emissions, contrail warming, delay warnings, operating
carrier notes, tree-absorption prose -- is ignored by not matching, so
new noise varieties cannot break parsing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Three-tier place-name resolution

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (Google Flights section)
- Create: `tests/test_gf_place_names.py`

**Interfaces:**
- Consumes: `_GF_LAYOVER` from Task 4.
- Produces: `_IATA_CITY: dict[str, str]`; `_harvest_layover_cities(text: str) -> dict[str, str]`; `_resolve_place_name(iata: str, airport_name: str, layover_cities: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gf_place_names.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gf_place_names.py -v`
Expected: FAIL with `AttributeError: module 'parse' has no attribute '_resolve_place_name'`.

- [ ] **Step 3: Implement place-name resolution**

Add below `_clean_gf_aircraft`:

```python
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
```

- [ ] **Step 4: Run tests; expect PASS**

Run: `uv run pytest tests/test_gf_place_names.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_gf_place_names.py
git commit -m "feat: resolve chunk-header place names in three tiers

Curated map, then a city harvested from any layover line in the paste,
then the airport name minus its trailing 'Airport'. The layover tier
keeps the map at two entries: KIX strips to 'Kansai International' but
its own paste says 'Osaka'.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Slice splitting and `parse_google_flights`

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (Google Flights section)
- Create: `tests/test_gf_parse.py`
- Create: `test-cases/test-case-gf-5-input.txt`

**Interfaces:**
- Consumes: `_infer_year`, all anchors, `_resolve_place_name`, `_harvest_layover_cities`, `_to_24h` (existing, :138).
- Produces: `_parse_gf_slices(text) -> list[str]`; `_gf_slice_base_date(block, not_before) -> Optional[date]`; `_gf_slice_price(block) -> tuple[Optional[str], Optional[Decimal]]`; `_gf_slice_trip_type(block) -> Optional[str]`; `_parse_gf_segments(block, base_date, layover_cities) -> list[Segment]`; `parse_google_flights(text, reference_date=None) -> Itinerary`

- [ ] **Step 1: Create the raw fixture input**

Create `test-cases/test-case-gf-5-input.txt` with exactly this content:

```
Departure
Wed, Aug 26
785 kg CO2e
+16% emissions
£1,387
round trip

6:15 AMLondon Stansted Airport (STN)
Travel time: 3 hr 55 min
12:10 PMIstanbul Airport (IST)
Turkish AirlinesEconomyBoeing 737TK 1246
Often delayed by 30+ min
Average legroom (31 in)
Wi-Fi for a fee
In-seat USB outlet
On-demand video
Emissions estimate: 226 kg CO2e
Contrail warming potential: Medium
14 hr 15 min layoverIstanbul (IST)Long layover

2:25 AM+1Istanbul Airport (IST)
Travel time: 10 hr 40 minOvernight
7:05 PM+1Kansai International Airport (KIX)
Turkish AirlinesEconomyBoeing 787TK 86
Average legroom (31 in)
Wi-Fi for a fee
In-seat USB outlet
On-demand video
Emissions estimate: 481 kg CO2e
Contrail warming potential: Low
1 hr 55 min layoverOsaka (KIX)

9:00 PM+1Kansai International Airport (KIX)
Travel time: 1 hr 20 min
10:20 PM+1Haneda Airport (HND)
ANAEconomyBoeing 737NH 98
Plane and crew by ANA Wings
Average legroom (31 in)
Free Wi-Fi
Stream media to your device
Emissions estimate: 78 kg CO2e
Contrail warming potential: Low
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_gf_parse.py`:

```python
"""parse_google_flights: slices, segments, dates, price."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)


def _gf5():
    return (TEST_CASES / "test-case-gf-5-input.txt").read_text(encoding="utf-8")


def test_single_slice_yields_one_chunk():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    assert it.source == "google_flights"
    assert len(it.chunks) == 1


def test_three_segments_in_order():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    segments = it.chunks[0].segments
    assert [s.flight_number for s in segments] == ["1246", "86", "98"]
    assert [s.airline for s in segments] == ["TK", "TK", "NH"]


def test_airports_and_resolved_city_names():
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].dep_airport == "STN"
    assert segments[0].dep_city == "London Stansted"
    assert segments[1].arr_airport == "KIX"
    assert segments[1].arr_city == "Osaka"       # tier 2, from a layover line
    assert segments[2].arr_city == "Tokyo"       # tier 1, curated map


def test_day_offset_counts_from_the_slice_date_not_cumulatively():
    """All three +1 markers mean Aug 27, even across two layovers."""
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].dep_datetime == datetime(2026, 8, 26, 6, 15)
    assert segments[0].arr_datetime == datetime(2026, 8, 26, 12, 10)
    assert segments[1].dep_datetime == datetime(2026, 8, 27, 2, 25)
    assert segments[1].arr_datetime == datetime(2026, 8, 27, 19, 5)
    assert segments[2].dep_datetime == datetime(2026, 8, 27, 21, 0)
    assert segments[2].arr_datetime == datetime(2026, 8, 27, 22, 20)


def test_cabin_and_aircraft():
    segments = parser.parse_google_flights(_gf5(), reference_date=REF).chunks[0].segments
    assert segments[0].fare_class == "Economy"
    assert segments[0].aircraft == "Boeing 737"
    assert segments[1].aircraft == "Boeing 787"


def test_price_currency_and_trip_type():
    it = parser.parse_google_flights(_gf5(), reference_date=REF)
    assert it.currency == "£"
    assert it.total_cost == Decimal("1387")
    assert it.trip_type == "round trip"


def test_two_slices_yield_two_chunks_and_the_last_price():
    text = (
        "Departure\nWed, Aug 26\n£1,497\nround trip\n"
        "7:00 PMHeathrow Airport (LHR)\n"
        "Travel time: 14 hr 15 minOvernight\n"
        "5:15 PM+1Haneda Airport (HND)\n"
        "ANAEconomyBoeing 777NH 212\n"
        "Return\nSun, Aug 30\n£1,355\nround trip\n"
        "12:40 PMHaneda Airport (HND)\n"
        "Travel time: 14 hr 45 min\n"
        "8:25 PMLeonardo da Vinci International Airport (FCO)\n"
        "ITAEconomyAirbus A350AZ 793\n"
    )
    it = parser.parse_google_flights(text, reference_date=REF)
    assert len(it.chunks) == 2
    assert it.total_cost == Decimal("1355")


def test_no_slice_header_yields_no_chunks():
    assert parser.parse_google_flights("nothing here", reference_date=REF).chunks == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_gf_parse.py -v`
Expected: FAIL with `AttributeError: module 'parse' has no attribute 'parse_google_flights'`.

- [ ] **Step 4: Implement slice splitting and the per-slice field readers**

Add below `_resolve_place_name`:

```python
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
        return date(year, month, int(day))
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
```

- [ ] **Step 5: Implement `_parse_gf_segments`**

```python
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
```

- [ ] **Step 6: Implement `parse_google_flights`**

```python
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
```

- [ ] **Step 7: Run tests; expect PASS**

Run: `uv run pytest tests/test_gf_parse.py -v`
Expected: all 8 PASS. If `test_day_offset_counts_from_the_slice_date_not_cumulatively` fails with dates on Aug 28, the offset is being accumulated instead of applied to `base_date`.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -v`
Expected: 100 passed.

- [ ] **Step 9: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_gf_parse.py \
        test-cases/test-case-gf-5-input.txt
git commit -m "feat: parse Google Flights pastes into Itinerary objects

Each Departure/Return slice becomes one Chunk directly, rather than
going through group_into_chunks: its 24h rule would split a longer
layover, and cross-timezone gap arithmetic is meaningless when every
printed time is local.

Arrival times come from the printed time plus the printed +N marker,
which counts from the slice date rather than accumulating -- the
STN-HND fixture holds at +1 across two layovers.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `render_google_flights`

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (Google Flights section)
- Create: `tests/test_gf_render.py`

**Interfaces:**
- Consumes: `parse_google_flights`, `_render_segment_line_google_flights`, `_render_chunk_header_email` (existing, :329), `_fmt_money`, `_SOURCE_LABEL`.
- Produces: `_render_itinerary_header_google_flights(it) -> str`; `render_google_flights(it) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gf_render.py`:

```python
"""render_google_flights output."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"
REF = date(2026, 8, 2)

EXPECTED_GF5 = """\
- Google Flights itinerary: £1,387 round trip.
  - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737)."""


def test_render_gf5():
    text = (TEST_CASES / "test-case-gf-5-input.txt").read_text(encoding="utf-8")
    it = parser.parse_google_flights(text, reference_date=REF)
    assert parser.render_google_flights(it) == EXPECTED_GF5


def test_header_without_price_or_trip_type():
    it = parser.Itinerary(source="google_flights")
    assert parser._render_itinerary_header_google_flights(it) == (
        "- Google Flights itinerary:")


def test_header_with_price_only():
    it = parser.Itinerary(
        source="google_flights", total_cost=Decimal("301"), currency="£")
    assert parser._render_itinerary_header_google_flights(it) == (
        "- Google Flights itinerary: £301.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gf_render.py -v`
Expected: FAIL with `AttributeError: module 'parse' has no attribute 'render_google_flights'`.

- [ ] **Step 3: Implement the renderer**

Add below `parse_google_flights`:

```python
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
```

- [ ] **Step 4: Run tests; expect PASS**

Run: `uv run pytest tests/test_gf_render.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_gf_render.py
git commit -m "feat: render Google Flights itineraries

Reuses the email chunk header verbatim and the shared segment-line
core, differing only in the header (currency symbol plus trip type)
and the parenthetical extras (cabin and aircraft rather than fare
class and seat).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Format detection and dispatch

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (`detect_format` at :82, `parse_united_itinerary` at :745)
- Modify: `tests/test_detect_format.py`

**Interfaces:**
- Consumes: `parse_google_flights`, `render_google_flights`.
- Produces: `parse_united_itinerary(text, reference_date=None) -> str`; `detect_format` returning `"google_flights"`.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_detect_format.py`:

```python
def test_google_flights_sample_detects_as_google_flights():
    text = _read("test-case-gf-5-input.txt")
    assert parser.detect_format(text) == "google_flights"


def test_google_flights_does_not_shadow_email():
    text = _read("test-case-email-FQZ1B5-popclip-input.txt")
    assert parser.detect_format(text) == "email"


def test_google_flights_does_not_shadow_reservation_ui():
    text = _read("test-case-6-popclip-input.txt")
    assert parser.detect_format(text) == "reservation_ui"


def test_end_to_end_dispatch_to_google_flights():
    from datetime import date
    text = _read("test-case-gf-5-input.txt")
    result = parser.parse_united_itinerary(text, reference_date=date(2026, 8, 2))
    assert result.startswith("- Google Flights itinerary: £1,387 round trip.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detect_format.py -v`
Expected: FAIL — `detect_format` returns `"unknown"` for the Google sample, and `parse_united_itinerary()` rejects the `reference_date` keyword.

- [ ] **Step 3: Add the `google_flights` branch to `detect_format`**

Replace the body of `detect_format` (:95-108) with:

```python
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
```

Update the docstring above it to document the new branch and that it is
checked first.

- [ ] **Step 4: Thread `reference_date` through `parse_united_itinerary`**

Replace the signature and the dispatch prologue (:745-756):

```python
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
        return render_google_flights(itinerary)

    if fmt == "email":
        return render_email(parse_email(text))
```

- [ ] **Step 5: Run the full suite; expect all PASS**

Run: `uv run pytest -v`
Expected: 107 passed.

- [ ] **Step 6: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_detect_format.py
git commit -m "feat: detect and dispatch Google Flights input

Keyed on the co-occurrence of 'Travel time:' and 'kg CO2e', checked
before the two United branches. No signature overlap, so the existing
paths are untouched -- covered by tests asserting the email and
reservation-UI samples still classify as before.

parse_united_itinerary gains an optional reference_date so fixtures do
not depend on the wall clock.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: End-to-end YAML fixtures

**Files:**
- Create: `test-cases/test-case-gf-{1,2,3,4,rt}-input.txt`
- Create: `test-cases/test-case-gf-{1,2,3,4,5,rt}.yaml`
- Create: `tests/test_gf_end_to_end.py`

**Interfaces:**
- Consumes: `parse_united_itinerary(text, reference_date=...)`, `load_yaml_case` from `tests/conftest.py`.

- [ ] **Step 1: Create the four remaining raw inputs**

`test-cases/test-case-gf-1-input.txt`:

```
Departure
Wed, Aug 26
171 kg CO2e
+82% emissions
£301
round trip
2:25 PMHeathrow Airport (LHR)
Travel time: 1 hr 40 min
5:05 PMGeneva Airport (GVA)
SWISSEconomyAirbus A220-300 PassengerLX 355
Below average legroom (29 in)
Emissions estimate: 88 kg CO2e
Contrail warming potential: Medium
1 hr 25 min layoverGeneva (GVA)
6:30 PMGeneva Airport (GVA)
Travel time: 1 hr 20 min
7:50 PMBiarritz Airport (BIQ)
SWISSEconomyAirbus A220-300 PassengerLX 2332
Below average legroom (29 in)
Emissions estimate: 83 kg CO2e
Contrail warming potential: Medium
Checked baggage not included in priceFare non-refundable, taxes may be refundableTicket changes for a fee
Bag and fare conditions depend on the return flight
```

`test-cases/test-case-gf-2-input.txt`:

```
Departure
Wed, Aug 26
810 kg CO2e
+20% emissions
£1,497
round trip
7:00 PMHeathrow Airport (LHR)
Travel time: 14 hr 15 minOvernight
5:15 PM+1Haneda Airport (HND)
ANAEconomyBoeing 777NH 212
Above average legroom (34 in)
Wi-Fi for a fee
In-seat power & USB outlets
On-demand video
Emissions estimate: 810 kg CO2e
Contrail warming potential: Low
```

`test-cases/test-case-gf-3-input.txt`:

```
Return
Sun, Aug 30
743 kg CO2e
+14% emissions
£1,355
round trip
12:40 PMHaneda Airport (HND)
Travel time: 14 hr 45 min
8:25 PMLeonardo da Vinci International Airport (FCO)
ITAEconomyAirbus A350AZ 793
Average legroom (31 in)
Wi-Fi for a fee
In-seat power & USB outlets
On-demand video
Emissions estimate: 567 kg CO2e
Contrail warming potential: Medium
10 hr 35 min layoverRome (FCO)Long layover
7:00 AM+1Leonardo da Vinci International Airport (FCO)
Travel time: 1 hr 10 min
8:10 AM+1Milan Linate Airport (LIN)
ITAEconomyAirbus A220-300 PassengerAZ 2010
Average legroom (30 in)
Wi-Fi for a fee
In-seat USB outlet
Emissions estimate: 62 kg CO2e
Contrail warming potential: Low
6 hr 55 min layoverMilan (LIN)Long layover
3:05 PM+1Milan Linate Airport (LIN)
Travel time: 1 hr 50 min
3:55 PM+1London City Airport (LCY)
ITAEconomyAirbus A220-100 PassengerAZ 238
Average legroom (30 in)
Wi-Fi for a fee
In-seat USB outlet
Emissions estimate: 114 kg CO2e
Contrail warming potential: Medium
```

`test-cases/test-case-gf-4-input.txt`:

```
Departure
Wed, Aug 26
112 kg CO2e
-10% emissions
£251
round trip
Avoids as much CO2e as 791 trees absorb in a day
10:30 AMHeathrow Airport (LHR)
Travel time: 2 hr 40 min
2:10 PMLeonardo da Vinci International Airport (FCO)
ITAEconomyAirbus A320neoAZ 203
Below average legroom (29 in)
Wi-Fi for a fee
In-seat USB outlet
Stream media to your device
Emissions estimate: 112 kg CO2e
Contrail warming potential: Medium
```

- [ ] **Step 2: Create the synthetic round-trip input**

`test-cases/test-case-gf-rt-input.txt` is `test-case-gf-2-input.txt` followed
immediately by `test-case-gf-3-input.txt`:

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
cat test-cases/test-case-gf-2-input.txt test-cases/test-case-gf-3-input.txt \
    > test-cases/test-case-gf-rt-input.txt
```

- [ ] **Step 3: Create the six YAML fixtures**

`test-cases/test-case-gf-1.yaml`:

```yaml
- description: "Google Flights: one stop, single airline (LHR > BIQ via GVA)"
  input_text_block_file: "test-case-gf-1-input.txt"
  expected_summary: |
    - Google Flights itinerary: £301 round trip.
      - Heathrow (LHR) to Biarritz (BIQ) (via Geneva (GVA)):
        - LHR > GVA LX 355: dep LHR Wed Aug 26, 2:25 pm, arr GVA 5:05 pm (Economy, Airbus A220-300).
        - GVA > BIQ LX 2332: dep GVA Wed Aug 26, 6:30 pm, arr BIQ 7:50 pm (Economy, Airbus A220-300).
```

`test-cases/test-case-gf-2.yaml`:

```yaml
- description: "Google Flights: nonstop, overnight, arrival crosses midnight"
  input_text_block_file: "test-case-gf-2-input.txt"
  expected_summary: |
    - Google Flights itinerary: £1,497 round trip.
      - Heathrow (LHR) to Tokyo (HND):
        - LHR > HND NH 212: dep LHR Wed Aug 26, 7:00 pm, arr HND Thu 5:15 pm (Economy, Boeing 777).
```

`test-cases/test-case-gf-3.yaml`:

```yaml
- description: "Google Flights: a Return slice, two stops, timezone-crossing final leg"
  input_text_block_file: "test-case-gf-3-input.txt"
  expected_summary: |
    - Google Flights itinerary: £1,355 round trip.
      - Tokyo (HND) to London City (LCY) (via Rome (FCO), Milan (LIN)):
        - HND > FCO AZ 793: dep HND Sun Aug 30, 12:40 pm, arr FCO 8:25 pm (Economy, Airbus A350).
        - FCO > LIN AZ 2010: dep FCO Mon Aug 31, 7:00 am, arr LIN 8:10 am (Economy, Airbus A220-300).
        - LIN > LCY AZ 238: dep LIN Mon Aug 31, 3:05 pm, arr LCY 3:55 pm (Economy, Airbus A220-100).
```

`test-cases/test-case-gf-4.yaml`:

```yaml
- description: "Google Flights: nonstop with tree-absorption prose and negative emissions"
  input_text_block_file: "test-case-gf-4-input.txt"
  expected_summary: |
    - Google Flights itinerary: £251 round trip.
      - Heathrow (LHR) to Rome (FCO):
        - LHR > FCO AZ 203: dep LHR Wed Aug 26, 10:30 am, arr FCO 2:10 pm (Economy, Airbus A320neo).
```

`test-cases/test-case-gf-5.yaml`:

```yaml
- description: "Google Flights: two stops, mixed airlines, blank lines, flat +1 across two layovers"
  input_text_block_file: "test-case-gf-5-input.txt"
  expected_summary: |
    - Google Flights itinerary: £1,387 round trip.
      - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
        - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
        - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
        - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737).
```

`test-cases/test-case-gf-rt.yaml`:

```yaml
- description: >-
    SYNTHETIC: gf-2 and gf-3 concatenated to exercise the two-slice path.
    Every real paste supplied so far has been a single slice, so no genuine
    Departure+Return copy was available. Structurally faithful (LHR>HND out,
    HND>LCY back) and exercises the differing-price branch, where the last
    slice's price wins. Replace with a real paste if one turns up.
  input_text_block_file: "test-case-gf-rt-input.txt"
  expected_summary: |
    - Google Flights itinerary: £1,355 round trip.
      - Heathrow (LHR) to Tokyo (HND):
        - LHR > HND NH 212: dep LHR Wed Aug 26, 7:00 pm, arr HND Thu 5:15 pm (Economy, Boeing 777).
      - Tokyo (HND) to London City (LCY) (via Rome (FCO), Milan (LIN)):
        - HND > FCO AZ 793: dep HND Sun Aug 30, 12:40 pm, arr FCO 8:25 pm (Economy, Airbus A350).
        - FCO > LIN AZ 2010: dep FCO Mon Aug 31, 7:00 am, arr LIN 8:10 am (Economy, Airbus A220-300).
        - LIN > LCY AZ 238: dep LIN Mon Aug 31, 3:05 pm, arr LCY 3:55 pm (Economy, Airbus A220-100).
```

- [ ] **Step 4: Write the end-to-end test**

Create `tests/test_gf_end_to_end.py`:

```python
"""End-to-end: parse_united_itinerary against the Google Flights fixtures."""
from __future__ import annotations

from datetime import date

import pytest

from tests.conftest import load_yaml_case

import parse as parser

# Pinned so year inference is deterministic. Without this the fixtures
# would depend on the wall clock: run in 2027, "Wed, Aug 26" finds no
# matching Wednesday nearby and renders the wrong weekday.
REF = date(2026, 8, 2)


@pytest.mark.parametrize("fixture_file", [
    "test-case-gf-1.yaml",
    "test-case-gf-2.yaml",
    "test-case-gf-3.yaml",
    "test-case-gf-4.yaml",
    "test-case-gf-5.yaml",
    "test-case-gf-rt.yaml",
])
def test_google_flights_fixture_end_to_end(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(
        case["input_text_block"], reference_date=REF)
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
```

- [ ] **Step 5: Run the fixtures**

Run: `uv run pytest tests/test_gf_end_to_end.py -v`
Expected: all 6 PASS.

If `test-case-gf-3` fails on `Milan Linate (LIN)` versus `Milan (LIN)`, the
layover tier is not being consulted: LIN appears as a layover in that same
paste, so tier 2 applies and `Milan` is correct.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: 113 passed.

- [ ] **Step 7: Commit**

```bash
git add test-cases/test-case-gf-* tests/test_gf_end_to_end.py
git commit -m "test: add end-to-end Google Flights fixtures

Five real pastes plus one synthetic two-slice concatenation. Between
them they cover nonstop, one stop and two stops; single and mixed
airlines; a Return slice; blank-line separators; a timezone-crossing
leg; +1 held flat across two layovers; and all three place-name tiers.

The reference date is pinned so year inference cannot drift with the
wall clock.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Manual verification and README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Confirm the bundle has no runtime dependencies**

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
grep -nE "^(import|from) " "United Itinerary.popclipext/parse.py"
```

Expected: only `os`, `re`, `dataclasses`, `datetime`, `decimal`, `typing`.
Any other module is a violation of the global constraint — stop and remove it.

- [ ] **Step 2: Confirm the file is still a single file and the symlink is intact**

```bash
ls -l summarize-united-itinerary.py
ls -1 "United Itinerary.popclipext/"
```

Expected: the symlink points at `United Itinerary.popclipext/parse.py`, and
the bundle contains only `Config.json` and `parse.py` (plus possibly
`.DS_Store` / `__pycache__`).

- [ ] **Step 3: Smoke test the CLI on real input**

```bash
./summarize-united-itinerary.py test-cases/test-case-gf-5-input.txt
```

Expected (note: this runs with today's date, not the pinned reference, so the
weekday must still read `Wed`/`Thu` — if it does not, `_infer_year`'s window
is too narrow):

```
- Google Flights itinerary: £1,387 round trip.
  - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737).
```

- [ ] **Step 4: Smoke test stdin and the United regression**

```bash
cat test-cases/test-case-gf-1-input.txt | ./summarize-united-itinerary.py
./summarize-united-itinerary.py test-cases/test-case-6-popclip-input.txt
```

Expected: the gf-1 summary, then the reservation-UI summary now headed
`- United.com itinerary: $3,248 + 62,500 miles`.

- [ ] **Step 5: Update `README.md`**

Replace the `## Output Format` section's example and add Google Flights to the
usage notes. Replace:

```markdown
## Output Format

```
- Itinerary: $2,207.63 + 40,000 miles
  - LHR > SFO UA 900: dep LHR Thu Feb 5, 10:05 am, arr SFO 1:20 pm (nonstop, 11h15m, Boeing 777-200ER).
  - SFO > LHR UA 901: dep SFO Wed Feb 11, 12:50 pm, arr LHR Thu 7:25 am (nonstop, 10h35m, Boeing 777-200).
```
```

with:

```markdown
## Supported Input

The format is detected automatically:

- **United.com reservation pages** — selected text from the flight selection UI
- **United eTicket / receipt emails** — selected text from Gmail
- **Google Flights** — selected text from a search result

## Output Format

United.com reservation page:

```
- United.com itinerary: $2,208 + 40,000 miles
  - LHR > SFO UA 900: dep LHR Thu Feb 5, 10:05 am, arr SFO 1:20 pm (nonstop, 11h15m, Boeing 777-200ER).
  - SFO > LHR UA 901: dep SFO Wed Feb 11, 12:50 pm, arr LHR Thu 7:25 am (nonstop, 10h35m, Boeing 777-200).
```

Google Flights:

```
- Google Flights itinerary: £1,387 round trip.
  - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737).
```

Google Flights omits the year, so it is inferred from the printed weekday.
```

- [ ] **Step 6: Run the full suite one final time**

Run: `uv run pytest -v`
Expected: 113 passed.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: document Google Flights as a third input format

Adds a Supported Input section listing all three sources and shows the
Google Flights output shape alongside the United one. Notes that the
year is inferred from the weekday, since Google omits it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 8: Manual PopClip install test (user-driven)**

Instruct the user:

> Double-click `United Itinerary.popclipext` in Finder so PopClip picks up the
> update. Then select a Google Flights search result in your browser and run
> the action. The summary should land on the clipboard headed
> `- Google Flights itinerary:`.

If it fails, check PopClip's console and confirm the script runs standalone
under the *system* interpreter rather than the uv venv:

```bash
/usr/bin/python3 "United Itinerary.popclipext/parse.py" \
    test-cases/test-case-gf-5-input.txt
```

This is the real constraint check — it must work with no virtualenv active.
