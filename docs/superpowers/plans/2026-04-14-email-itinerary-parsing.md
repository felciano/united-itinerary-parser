# Email Itinerary Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the United itinerary parser to handle eTicket/Receipt emails (selected + PopClip-copied from Gmail) in addition to the existing reservation-UI text, producing a nested summary grouped by trip chunks.

**Architecture:** Single-file `parse.py` inside the PopClip bundle, with project-root `summarize-united-itinerary.py` as a symlink. Intermediate `Itinerary`/`Chunk`/`Segment` dataclasses separate parsing from rendering. Two parsers (`parse_reservation_ui`, `parse_email`) produce `Itinerary` objects; two renderers (`render_reservation_ui`, `render_email`) turn them back into text. A `detect_format` dispatcher picks the right pair.

**Tech Stack:** Python 3.9+ (stdlib only in `parse.py` — no runtime deps, the PopClip bundle must install as-is); `pytest` + `PyYAML` as dev deps; `uv` for environment management.

---

## Pre-work: Stash unrelated uncommitted changes

The working tree has in-progress edits to `United Itinerary.popclipext/parse.py` and `summarize-united-itinerary.py` from earlier work. Those edits are superseded by this plan (we're rewriting both files). Before starting, confirm the baseline.

- [ ] **Verify current git state**

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
git status
git diff --stat
```

Expected: `United Itinerary.popclipext/parse.py` and `summarize-united-itinerary.py` modified; untracked files include `test-cases/test-case-6-input.txt`, `test-case-6-popclip-input.txt`, `test-cases/test-case-email-FQZ1B5-popclip-input.txt`, `test-cases/test-case-email-NLY82V-popclip-input.txt`, `.claude/`.

- [ ] **Stash uncommitted edits so snapshot tests reflect the last committed parser**

```bash
git stash push -m "pre-refactor: WIP parse.py/CLI edits, will be superseded" \
  "United Itinerary.popclipext/parse.py" "summarize-united-itinerary.py"
git status
```

Expected: `parse.py` and `summarize-united-itinerary.py` no longer appear as modified. Untracked test-case files remain.

*Note: the stash is a safety net only — after the refactor these WIP changes won't be restored. We can `git stash drop` at the end.*

---

## Task 1: Add pytest + PyYAML as dev dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dev dependencies via uv**

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
uv add --dev pytest pyyaml
```

Expected: `pyproject.toml` gets a `[dependency-groups]` / `dev = [...]` entry (or equivalent depending on uv version); a `uv.lock` is generated.

- [ ] **Step 2: Verify pytest runs**

```bash
uv run pytest --version
```

Expected: prints a pytest version string, no error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest and pyyaml as dev dependencies

Sets up the test harness for the email-parsing work. Runtime stays
stdlib-only so the PopClip bundle installs without pip.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Baseline snapshot test against existing reservation-UI fixtures

Goal: pin the current reservation-UI output so later refactoring doesn't silently regress. We do this *before* touching `parse.py` so we're comparing against the committed baseline.

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_reservation_ui_snapshot.py`

- [ ] **Step 1: Create empty `tests/__init__.py`**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Create `tests/conftest.py`** with a fixture loader that reads YAML test cases

```python
"""Shared pytest fixtures for itinerary parser tests."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES_DIR = REPO_ROOT / "test-cases"
POPCLIP_BUNDLE = REPO_ROOT / "United Itinerary.popclipext"

# Make the PopClip bundle importable as a package path
sys.path.insert(0, str(POPCLIP_BUNDLE))


def load_yaml_case(filename: str) -> dict[str, Any]:
    """Load a YAML test case from test-cases/."""
    path = TEST_CASES_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Existing YAML files are a list with a single dict
    if isinstance(data, list):
        return data[0]
    return data
```

- [ ] **Step 3: Create `tests/test_reservation_ui_snapshot.py`**

```python
"""Snapshot tests: existing reservation-UI output must stay byte-identical
across the refactor. If one of these fails after refactoring, the renderer
has drifted from the baseline."""
from __future__ import annotations

import pytest

from tests.conftest import load_yaml_case

# Import the parser from the PopClip bundle (added to sys.path in conftest)
import parse as parser


@pytest.mark.parametrize("fixture_file", [
    "test-case-1.yaml",
    "test-case-2.yaml",
    "test-case-3.yaml",
    "test-case-4.yaml",
    "test-case-5.yaml",
])
def test_reservation_ui_output_matches_fixture(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(case["input_text_block"])
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
```

- [ ] **Step 4: Run snapshot tests; expect them to pass (or identify drift)**

```bash
uv run pytest tests/test_reservation_ui_snapshot.py -v
```

Expected: all 5 pass. If any fail, *do not proceed* — the fixture expectations have drifted from the current parser output. Triage: read the diff, decide whether the fixture or the parser is right, update whichever is wrong, commit that fix as a separate commit before proceeding.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add baseline snapshot tests for reservation-UI output

Pins the current output of parse_united_itinerary() against the
existing YAML fixtures so later refactoring cannot silently regress
the reservation-UI format.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add `Segment`, `Chunk`, `Itinerary` dataclasses

**Files:**
- Modify: `United Itinerary.popclipext/parse.py` (add dataclasses near the top)
- Create: `tests/test_data_model.py`

- [ ] **Step 1: Write failing test for dataclass construction**

Create `tests/test_data_model.py`:

```python
"""Unit tests for the Itinerary/Chunk/Segment data model."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import parse as parser


def test_segment_construction():
    s = parser.Segment(
        flight_number="17",
        dep_airport="LHR",
        dep_city="London",
        arr_airport="EWR",
        arr_city="Newark",
        dep_datetime=datetime(2026, 4, 26, 10, 25),
        arr_datetime=datetime(2026, 4, 26, 13, 20),
        fare_class="Economy W",
        seat="33K",
        aircraft=None,
        duration=None,
    )
    assert s.dep_airport == "LHR"
    assert s.seat == "33K"


def test_chunk_construction():
    s = parser.Segment(
        flight_number="924", dep_airport="IAD", dep_city="Washington",
        arr_airport="LHR", arr_city="London",
        dep_datetime=datetime(2026, 3, 11, 23, 15),
        arr_datetime=datetime(2026, 3, 12, 10, 50),
        fare_class="Economy V", seat="35F", aircraft=None, duration=None,
    )
    c = parser.Chunk(segments=[s], total_duration=None)
    assert len(c.segments) == 1


def test_itinerary_construction():
    it = parser.Itinerary(
        source="email",
        chunks=[],
        total_cost=Decimal("556.50"),
        miles=None,
        plus_points=None,
        confirmation_number="NLY82V",
        eticket_number="0162379511080",
        upgrade_fees=None,
        accrual_award_miles=4707,
        accrual_pqp=523,
        accrual_pqf=1,
    )
    assert it.confirmation_number == "NLY82V"
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_data_model.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute 'Segment'`.

- [ ] **Step 3: Add dataclasses to `United Itinerary.popclipext/parse.py`**

Insert just below the module docstring (line 3), before any existing code:

```python
from __future__ import annotations

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
    segments: list[Segment]
    total_duration: Optional[timedelta] = None


@dataclass
class Itinerary:
    source: str  # "reservation_ui" | "email"
    chunks: list[Chunk] = field(default_factory=list)
    total_cost: Optional[Decimal] = None
    miles: Optional[int] = None
    plus_points: Optional[int] = None
    confirmation_number: Optional[str] = None
    eticket_number: Optional[str] = None
    upgrade_fees: Optional[Decimal] = None
    accrual_award_miles: Optional[int] = None
    accrual_pqp: Optional[int] = None
    accrual_pqf: Optional[int] = None
```

- [ ] **Step 4: Run tests; expect all data model tests to pass and snapshot tests still pass**

```bash
uv run pytest -v
```

Expected: data model tests PASS, snapshot tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_data_model.py
git commit -m "feat: add Itinerary/Chunk/Segment dataclasses

Introduces the intermediate data model that both parsers (reservation
UI and email) will produce, and that the renderers will consume.
Standard library only.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Implement `group_into_chunks()`

Pure function: takes a list of `Segment` in chronological order, returns a list of `Chunk`. Walks adjacent pairs; same chunk iff `arr_airport == dep_airport` AND gap ≤ 24h.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `tests/test_chunk_grouping.py`

- [ ] **Step 1: Write failing tests**

```python
"""Unit tests for group_into_chunks."""
from __future__ import annotations

from datetime import datetime, timedelta

import parse as parser


def _seg(flight: str, dep: str, arr: str, dep_dt: datetime, arr_dt: datetime):
    return parser.Segment(
        flight_number=flight, dep_airport=dep, dep_city=None,
        arr_airport=arr, arr_city=None,
        dep_datetime=dep_dt, arr_datetime=arr_dt,
    )


def test_empty_list_produces_no_chunks():
    assert parser.group_into_chunks([]) == []


def test_single_segment_is_one_chunk():
    s = _seg("924", "IAD", "LHR",
             datetime(2026, 3, 11, 23, 15), datetime(2026, 3, 12, 10, 50))
    chunks = parser.group_into_chunks([s])
    assert len(chunks) == 1
    assert chunks[0].segments == [s]


def test_connection_within_24h_same_chunk():
    # LHR→EWR arr Sun 1:20pm, EWR→PUJ dep Mon 8:11am ≈ 19h → same chunk
    s1 = _seg("17", "LHR", "EWR",
              datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20))
    s2 = _seg("1514", "EWR", "PUJ",
              datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 1
    assert chunks[0].segments == [s1, s2]


def test_stopover_over_24h_new_chunk():
    # PUJ destination stay: ~74h between arr and next dep
    s1 = _seg("1514", "EWR", "PUJ",
              datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15))
    s2 = _seg("524", "PUJ", "IAH",
              datetime(2026, 4, 30, 14, 20), datetime(2026, 4, 30, 18, 4))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 2


def test_airport_mismatch_new_chunk():
    # Even with small time gap, mismatched airports means new chunk
    s1 = _seg("17", "LHR", "EWR",
              datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20))
    s2 = _seg("X", "JFK", "LAX",
              datetime(2026, 4, 26, 14, 0), datetime(2026, 4, 26, 19, 0))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 2


def test_exactly_24h_boundary_same_chunk():
    # Gap of exactly 24h should still be same chunk (≤24h inclusive)
    s1 = _seg("A", "AAA", "BBB",
              datetime(2026, 1, 1, 10, 0), datetime(2026, 1, 1, 12, 0))
    s2 = _seg("B", "BBB", "CCC",
              datetime(2026, 1, 2, 12, 0), datetime(2026, 1, 2, 14, 0))
    chunks = parser.group_into_chunks([s1, s2])
    assert len(chunks) == 1


def test_real_itinerary_FQZ1B5_shape():
    # 4 segments: LHR-EWR, EWR-PUJ, PUJ-IAH, IAH-LHR
    # Expected chunks: [LHR-EWR-PUJ], [PUJ-IAH-LHR]
    s = [
        _seg("17", "LHR", "EWR",
             datetime(2026, 4, 26, 10, 25), datetime(2026, 4, 26, 13, 20)),
        _seg("1514", "EWR", "PUJ",
             datetime(2026, 4, 27, 8, 11), datetime(2026, 4, 27, 12, 15)),
        _seg("524", "PUJ", "IAH",
             datetime(2026, 4, 30, 14, 20), datetime(2026, 4, 30, 18, 4)),
        _seg("5", "IAH", "LHR",
             datetime(2026, 4, 30, 20, 5), datetime(2026, 5, 1, 11, 35)),
    ]
    chunks = parser.group_into_chunks(s)
    assert len(chunks) == 2
    assert [seg.flight_number for seg in chunks[0].segments] == ["17", "1514"]
    assert [seg.flight_number for seg in chunks[1].segments] == ["524", "5"]
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_chunk_grouping.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute 'group_into_chunks'`.

- [ ] **Step 3: Implement `group_into_chunks`**

Add to `parse.py` below the dataclass definitions:

```python
CHUNK_GAP_THRESHOLD = timedelta(hours=24)


def group_into_chunks(segments: list[Segment]) -> list[Chunk]:
    """Group consecutive segments into trip chunks.

    Two segments belong to the same chunk iff the first's arrival airport
    matches the second's departure airport AND the time gap between them
    is ≤ 24 hours. Otherwise the second starts a new chunk.
    """
    if not segments:
        return []

    chunks: list[Chunk] = []
    current: list[Segment] = [segments[0]]

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
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_chunk_grouping.py -v
```

Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_chunk_grouping.py
git commit -m "feat: add group_into_chunks with 24h connection/stopover rule

Splits a chronologically-ordered segment list into trip chunks using
the IATA convention: same chunk if arr_airport matches next dep_airport
and the gap is within 24 hours; otherwise new chunk.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Implement `detect_format()`

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `tests/test_detect_format.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_detect_format.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute 'detect_format'`.

- [ ] **Step 3: Implement `detect_format`**

Add to `parse.py` below `group_into_chunks`:

```python
def detect_format(text: str) -> str:
    """Classify the input text as 'email', 'reservation_ui', or 'unknown'.

    Email signatures: both 'Thank you for choosing United' and
    'Confirmation Number:' appear (the combination rarely occurs
    coincidentally in reservation-UI text).

    Reservation-UI signatures: any of 'Flight selection list',
    'Aircraft type:', or 'Duration:' appears.

    If both match, email wins (more specific). If neither matches, 'unknown'.
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
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_detect_format.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_detect_format.py
git commit -m "feat: add detect_format classifier

Returns 'email', 'reservation_ui', or 'unknown' based on content
signatures. Email takes precedence when both match.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Implement email segment parser

Parses the flight blocks from an email body into `Segment` objects. Leaves seats, fare class attachment to Traveler Details section (next task); this task attaches fare class from the flight header only.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `tests/test_parse_email_segments.py`

- [ ] **Step 1: Write failing test**

```python
"""Parse email flight blocks into Segments."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"


def test_parse_email_segments_NLY82V_single_flight():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    assert len(segments) == 1
    s = segments[0]
    assert s.flight_number == "924"
    assert s.dep_airport == "IAD"
    assert s.dep_city == "Washington"
    assert s.arr_airport == "LHR"
    assert s.arr_city == "London"
    assert s.dep_datetime == datetime(2026, 3, 11, 23, 15)
    assert s.arr_datetime == datetime(2026, 3, 12, 10, 50)
    assert s.fare_class == "Economy V"


def test_parse_email_segments_FQZ1B5_multi_flight():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    assert [s.flight_number for s in segments] == ["17", "1514", "524", "5"]
    assert segments[0].dep_city == "London"
    # Newark, NJ/New York, NY, US (EWR) → "Newark" (text before first comma)
    assert segments[0].arr_city == "Newark"
    assert segments[0].arr_airport == "EWR"
    # PUJ→IAH 2:20 PM → 6:04 PM same day
    assert segments[2].dep_datetime == datetime(2026, 4, 30, 14, 20)
    assert segments[2].arr_datetime == datetime(2026, 4, 30, 18, 4)
    # IAH→LHR crosses midnight: Thu 8:05 PM → Fri 11:35 AM
    assert segments[3].dep_datetime == datetime(2026, 4, 30, 20, 5)
    assert segments[3].arr_datetime == datetime(2026, 5, 1, 11, 35)
    # Fare class codes: all segments in FQZ1B5 are Economy W or S
    assert segments[0].fare_class == "Economy W"
    assert segments[2].fare_class == "Economy S"
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_parse_email_segments.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute '_parse_email_segments'`.

- [ ] **Step 3: Implement `_parse_email_segments`**

Add to `parse.py` below `detect_format`:

```python
import re as _re  # already imported at top; alias only if not

_EMAIL_FLIGHT_HEADER = _re.compile(
    r"Flight (\d+) of (\d+)\s+UA(\d+)\s*(?:\t+|\s{2,})Class:\s*(.+?)\s*\(([A-Z]+)\)"
)
_DATE_LINE = _re.compile(
    r"^[A-Za-z]{3},\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", _re.MULTILINE
)
_TIME_LINE = _re.compile(r"^(\d{1,2}):(\d{2})\s*([APap][Mm])", _re.MULTILINE)
_CITY_LINE = _re.compile(r"^([^\t\n(]+?)\s*\(([A-Z]{3})\)", _re.MULTILINE)

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}


def _first_city_name(raw: str) -> str:
    """Extract city from 'Newark, NJ/New York, NY, US' style label (text up to first comma)."""
    return raw.split(",", 1)[0].strip()


def _to_24h(hour: int, minute: int, meridiem: str) -> tuple[int, int]:
    meridiem = meridiem.upper()
    if meridiem == "AM":
        return (0 if hour == 12 else hour, minute)
    return (hour if hour == 12 else hour + 12, minute)


def _parse_email_segments(text: str) -> list[Segment]:
    """Split an email body on 'Flight N of M' markers and parse each block.

    Each block follows the tab-separated HTML table copy pattern:
        Flight N of M UA<num>\tClass: United <name> (<code>)
        <Weekday>, <Mon DD, YYYY>\t<Weekday>, <Mon DD, YYYY>
        HH:MM AM/PM\tHH:MM AM/PM
        <DepCity, ..., Country (IATA)>\t<ArrCity, ..., Country (IATA)>
    """
    headers = list(_EMAIL_FLIGHT_HEADER.finditer(text))
    if not headers:
        return []

    segments: list[Segment] = []
    for idx, m in enumerate(headers):
        start = m.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[start:end]

        dates = _DATE_LINE.findall(body)
        times = _TIME_LINE.findall(body)
        cities = _CITY_LINE.findall(body)
        if len(dates) < 2 or len(times) < 2 or len(cities) < 2:
            # Skip malformed section; don't raise — error handling parity with
            # the existing parser's best-effort approach.
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
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_parse_email_segments.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_parse_email_segments.py
git commit -m "feat: parse email flight blocks into Segments

Handles tab-separated date/time/city rows from the Gmail copy-paste
of a United eTicket email. Normalizes fare class ('United Economy (W)'
becomes 'Economy W') and extracts city as text before first comma.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Attach seat assignments to segments

Seats are listed in the Traveler Details block, one per airport pair (e.g., `Seats: LHR-EWR 33K` for the first segment, bare `EWR-PUJ 09D` for subsequent). Match by airport pair.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Modify: `tests/test_parse_email_segments.py`

- [ ] **Step 1: Extend tests to assert seat values**

Append to `tests/test_parse_email_segments.py`:

```python
def test_parse_email_attaches_seats_NLY82V():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    parser._attach_seats_from_traveler_details(text, segments)
    assert segments[0].seat == "35F"


def test_parse_email_attaches_seats_FQZ1B5():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    segments = parser._parse_email_segments(text)
    parser._attach_seats_from_traveler_details(text, segments)
    # Seats block:
    #   Seats: LHR-EWR 33K
    #   EWR-PUJ 09D
    #   PUJ-IAH 09D
    #   IAH-LHR 32G
    assert segments[0].seat == "33K"
    assert segments[1].seat == "09D"
    assert segments[2].seat == "09D"
    assert segments[3].seat == "32G"
```

- [ ] **Step 2: Run tests; expect failure**

```bash
uv run pytest tests/test_parse_email_segments.py::test_parse_email_attaches_seats_NLY82V -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute '_attach_seats_from_traveler_details'`.

- [ ] **Step 3: Implement `_attach_seats_from_traveler_details`**

Add to `parse.py` below `_parse_email_segments`:

```python
_SEAT_PAIR = _re.compile(r"([A-Z]{3})-([A-Z]{3})\s+([0-9]{1,3}[A-Z])")


def _attach_seats_from_traveler_details(text: str, segments: list[Segment]) -> None:
    """Parse seat assignments from the Traveler Details block and attach by
    airport pair. Mutates segments in place."""
    # Confine to the region between "Traveler Details" and the next major
    # section ("Purchase Summary" or "Additional Purchase Summary").
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

    seats_by_pair: dict[tuple[str, str], str] = {}
    for match in _SEAT_PAIR.finditer(region):
        dep, arr, seat = match.groups()
        seats_by_pair.setdefault((dep, arr), seat)

    for seg in segments:
        seg.seat = seats_by_pair.get((seg.dep_airport, seg.arr_airport))
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_parse_email_segments.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_parse_email_segments.py
git commit -m "feat: attach seat assignments from Traveler Details block

Maps 'IATA-IATA SEAT' pairs to segments by matching airport pair.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Parse itinerary-level fields (confirmation, eTicket, totals, accrual)

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `tests/test_parse_email_itinerary_fields.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for parse_email itinerary-level field extraction."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import parse as parser

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES = REPO_ROOT / "test-cases"


def test_parse_email_NLY82V_itinerary_fields():
    text = (TEST_CASES / "test-case-email-NLY82V-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert it.source == "email"
    assert it.confirmation_number == "NLY82V"
    assert it.eticket_number == "0162379511080"
    assert it.total_cost == Decimal("556.50")
    assert it.upgrade_fees is None
    assert it.accrual_award_miles == 4707
    assert it.accrual_pqp == 523
    assert it.accrual_pqf == 1


def test_parse_email_FQZ1B5_itinerary_fields():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    assert it.confirmation_number == "FQZ1B5"
    assert it.eticket_number == "0162389632983"
    # Base ticket total
    assert it.total_cost == Decimal("2564.60")
    # Two "Additional Purchase Summary" blocks at 550 each
    assert it.upgrade_fees == Decimal("1100.00")
    assert it.accrual_award_miles == 21510
    assert it.accrual_pqp == 2151
    assert it.accrual_pqf == 4


def test_parse_email_FQZ1B5_chunks():
    text = (TEST_CASES / "test-case-email-FQZ1B5-popclip-input.txt").read_text()
    it = parser.parse_email(text)
    # 4 segments grouped into 2 chunks by the 24h rule
    assert len(it.chunks) == 2
    assert [s.flight_number for s in it.chunks[0].segments] == ["17", "1514"]
    assert [s.flight_number for s in it.chunks[1].segments] == ["524", "5"]
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_parse_email_itinerary_fields.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute 'parse_email'`.

- [ ] **Step 3: Implement `parse_email`**

Add to `parse.py` below `_attach_seats_from_traveler_details`:

```python
_CONF_NUMBER = _re.compile(r"Confirmation Number:\s*\n\s*([A-Z0-9]{6})")
_ETICKET = _re.compile(r"eTicket number:\s*([0-9]+)")
_TOTAL_LINE = _re.compile(r"^Total:\s+([\d,]+\.\d{2})\s*USD", _re.MULTILINE)
_ACCRUAL_TOTALS = _re.compile(
    r"MileagePlus accrual totals:\s*\t?\s*([\d,]+)\s+([\d,]+)\s+(\d+)"
)


def _decimal_or_none(s: Optional[str]) -> Optional[Decimal]:
    if s is None:
        return None
    return Decimal(s.replace(",", ""))


def _int_or_none(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    return int(s.replace(",", ""))


def parse_email(text: str) -> Itinerary:
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
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_parse_email_itinerary_fields.py -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_parse_email_itinerary_fields.py
git commit -m "feat: parse_email composes Segment+Chunk+Itinerary

Extracts confirmation number, eTicket, total cost, upgrade fees,
and MileagePlus accrual totals, and calls group_into_chunks() to
produce the final Itinerary.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Implement `render_email()`

Produces the nested output format documented in the spec.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `tests/test_render_email.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run test; expect failure**

```bash
uv run pytest tests/test_render_email.py -v
```

Expected: FAIL with `AttributeError: module 'parse' has no attribute 'render_email'`.

- [ ] **Step 3: Implement `render_email`**

Add to `parse.py` below `parse_email`:

```python
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_SHORT = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_time_12h(dt: datetime) -> str:
    """Format time as '10:25 am' / '4:35 pm' (no leading zero on hour)."""
    hour = dt.hour % 12 or 12
    meridiem = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt.minute:02d} {meridiem}"


def _fmt_money(amount: Decimal) -> str:
    """Format as '$2,564.60'."""
    return f"${amount:,.2f}"


def _render_segment_line_email(seg: Segment) -> str:
    dep_weekday = _WEEKDAY_SHORT[seg.dep_datetime.weekday()]
    dep_month = _MONTH_SHORT[seg.dep_datetime.month]
    dep_day = seg.dep_datetime.day
    dep_time = _fmt_time_12h(seg.dep_datetime)
    arr_time = _fmt_time_12h(seg.arr_datetime)

    arr_prefix = ""
    if seg.arr_datetime.date() != seg.dep_datetime.date():
        arr_prefix = f" {_WEEKDAY_SHORT[seg.arr_datetime.weekday()]}"

    extras = []
    if seg.fare_class:
        extras.append(seg.fare_class)
    if seg.seat:
        extras.append(f"seat {seg.seat}")
    extra_str = f" ({', '.join(extras)})" if extras else ""

    return (
        f"    - {seg.dep_airport} > {seg.arr_airport} UA {seg.flight_number}: "
        f"dep {seg.dep_airport} {dep_weekday} {dep_month} {dep_day}, {dep_time}, "
        f"arr {seg.arr_airport}{arr_prefix} {arr_time}{extra_str}."
    )


def _render_chunk_header_email(chunk: Chunk) -> str:
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


def _render_itinerary_header_email(it: Itinerary) -> str:
    parts = [f"- Itinerary"]
    if it.confirmation_number:
        parts.append(f" {it.confirmation_number}")
    parts.append(":")

    after: list[str] = []
    if it.total_cost is not None:
        cost_piece = _fmt_money(it.total_cost)
        if it.upgrade_fees:
            cost_piece += f" + {_fmt_money(it.upgrade_fees)} upgrades"
        after.append(cost_piece)
    if it.eticket_number:
        after.append(f"(eTicket {it.eticket_number})")

    line = "".join(parts)
    if after:
        line += " " + " ".join(after)
        # Ensure a terminating period before an optional accrual sentence.
        if not line.endswith("."):
            line += "."

    if it.accrual_award_miles is not None:
        line += (
            f" Accrual: {it.accrual_award_miles:,} miles "
            f"/ {it.accrual_pqp:,} PQP / {it.accrual_pqf} PQF."
        )

    return line


def render_email(it: Itinerary) -> str:
    lines = [_render_itinerary_header_email(it)]
    for chunk in it.chunks:
        lines.append(_render_chunk_header_email(chunk))
        for seg in chunk.segments:
            lines.append(_render_segment_line_email(seg))
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests; expect all to pass**

```bash
uv run pytest tests/test_render_email.py -v
```

Expected: both PASS. If the formatting differs (spacing, punctuation), fix the renderer — the expected strings in the test are the spec.

- [ ] **Step 5: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/test_render_email.py
git commit -m "feat: render_email produces nested itinerary/chunk/segment output

Emits three-level indented output with city names in chunk headers,
terse IATA codes on segment lines, arrival weekday suffix when the
date crosses midnight, and an accrual sentence when present.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Wire up email path in `parse_united_itinerary()`

Add format dispatch so `parse_united_itinerary` (the existing entry point used by PopClip and CLI) routes email input to the new pipeline while reservation-UI input continues to use the existing path.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`
- Create: `test-cases/test-case-email-NLY82V.yaml`
- Create: `test-cases/test-case-email-FQZ1B5.yaml`
- Create: `tests/test_parse_united_itinerary_email.py`

- [ ] **Step 1: Create YAML fixtures**

Create `test-cases/test-case-email-NLY82V.yaml`:

```yaml
- description: "United eTicket email, single nonstop segment (IAD > LHR)"
  input_text_block_file: "test-case-email-NLY82V-popclip-input.txt"
  expected_summary: |
    - Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
      - Washington (IAD) to London (LHR):
        - IAD > LHR UA 924: dep IAD Wed Mar 11, 11:15 pm, arr LHR Thu 10:50 am (Economy V, seat 35F).
```

Create `test-cases/test-case-email-FQZ1B5.yaml`:

```yaml
- description: "United eTicket email, 4 segments, 2 chunks, upgrade fees"
  input_text_block_file: "test-case-email-FQZ1B5-popclip-input.txt"
  expected_summary: |
    - Itinerary FQZ1B5: $2,564.60 + $1,100.00 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.
      - London (LHR) to Punta Cana (PUJ) (via Newark (EWR)):
        - LHR > EWR UA 17: dep LHR Sun Apr 26, 10:25 am, arr EWR 1:20 pm (Economy W, seat 33K).
        - EWR > PUJ UA 1514: dep EWR Mon Apr 27, 8:11 am, arr PUJ 12:15 pm (Economy W, seat 09D).
      - Punta Cana (PUJ) to London (LHR) (via Houston (IAH)):
        - PUJ > IAH UA 524: dep PUJ Thu Apr 30, 2:20 pm, arr IAH 6:04 pm (Economy S, seat 09D).
        - IAH > LHR UA 5: dep IAH Thu Apr 30, 8:05 pm, arr LHR Fri 11:35 am (Economy S, seat 32G).
```

*Note: these fixtures use a new `input_text_block_file` key referencing the popclip-input.txt files (which are too large to inline cleanly). The conftest loader will support both `input_text_block` and `input_text_block_file`.*

- [ ] **Step 2: Extend `tests/conftest.py` to support `input_text_block_file`**

Replace the `load_yaml_case` function in `tests/conftest.py` with:

```python
def load_yaml_case(filename: str) -> dict[str, Any]:
    """Load a YAML test case from test-cases/.

    Supports two input keys:
    - input_text_block: inline literal block
    - input_text_block_file: sibling filename under test-cases/
    """
    path = TEST_CASES_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, list):
        data = data[0]
    if "input_text_block_file" in data and "input_text_block" not in data:
        ref = TEST_CASES_DIR / data["input_text_block_file"]
        data["input_text_block"] = ref.read_text(encoding="utf-8")
    return data
```

- [ ] **Step 3: Write failing test for email dispatch through `parse_united_itinerary`**

Create `tests/test_parse_united_itinerary_email.py`:

```python
"""End-to-end: parse_united_itinerary dispatches email input correctly."""
from __future__ import annotations

import pytest

from tests.conftest import load_yaml_case

import parse as parser


@pytest.mark.parametrize("fixture_file", [
    "test-case-email-NLY82V.yaml",
    "test-case-email-FQZ1B5.yaml",
])
def test_email_fixture_end_to_end(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)
    result = parser.parse_united_itinerary(case["input_text_block"])
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
```

- [ ] **Step 4: Run test; expect failure**

```bash
uv run pytest tests/test_parse_united_itinerary_email.py -v
```

Expected: FAIL — the current `parse_united_itinerary` doesn't know about emails; it will return an empty string or the wrong output.

- [ ] **Step 5: Wire up dispatch in `parse_united_itinerary`**

Edit `parse_united_itinerary` in `parse.py`. Find the existing function (near the bottom) and prepend a dispatch check for email:

```python
def parse_united_itinerary(text: str) -> str:
    """Convert a United itinerary to a terse summary. Supports reservation-UI
    text (two variants) and eTicket receipt emails."""

    # NEW: email dispatch
    if detect_format(text) == "email":
        itinerary = parse_email(text)
        return render_email(itinerary)

    # (existing reservation-UI code stays here, unchanged)
    ...
```

The rest of the existing function body (PopClip-vs-original detection, regex work, cost matching, header composition) remains as it is.

- [ ] **Step 6: Run all tests; expect all passes**

```bash
uv run pytest -v
```

Expected: email tests PASS, snapshot tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add "United Itinerary.popclipext/parse.py" tests/conftest.py \
        tests/test_parse_united_itinerary_email.py \
        test-cases/test-case-email-NLY82V.yaml \
        test-cases/test-case-email-FQZ1B5.yaml
git commit -m "feat: route email input through new parse_email + render_email

parse_united_itinerary() now detects emails and dispatches to the
new pipeline. Reservation-UI input continues through the existing
code path unchanged.

Adds end-to-end YAML fixtures for both email samples.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Add file/stdin/clipboard I/O to the PopClip bundle script

Currently `parse.py` reads only from `POPCLIP_TEXT`. The old CLI (`summarize-united-itinerary.py`) had file/stdin/pbpaste handling. We're about to symlink the CLI to `parse.py`, so the I/O handling moves here.

**Files:**
- Modify: `United Itinerary.popclipext/parse.py`

- [ ] **Step 1: Replace the `if __name__ == "__main__":` block at the bottom of `parse.py`** with the full CLI entry point

Replace this existing block:

```python
if __name__ == "__main__":
    text = os.environ.get("POPCLIP_TEXT", "")
    if text:
        result = parse_united_itinerary(text)
        if result:
            print(result)
```

With:

```python
def _get_input() -> tuple[str, bool]:
    """Return (text, from_clipboard). Sources in priority order:
    1. POPCLIP_TEXT env var (PopClip invocation)
    2. File argv[1] (CLI file mode)
    3. stdin if piped
    4. pbpaste (macOS clipboard fallback)
    """
    import os
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


def _output_result(text: str, to_clipboard: bool) -> None:
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


def main() -> None:
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
```

*The `os` import at top of file covers the env var read above. `subprocess` and `sys` are imported inline inside the helper functions to keep module import time fast for the pytest path.*

- [ ] **Step 2: Verify tests still pass**

```bash
uv run pytest -v
```

Expected: all PASS.

- [ ] **Step 3: Manual smoke test — file input**

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
uv run python "United Itinerary.popclipext/parse.py" test-cases/test-case-email-NLY82V-popclip-input.txt
```

Expected output:

```
- Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
  - Washington (IAD) to London (LHR):
    - IAD > LHR UA 924: dep IAD Wed Mar 11, 11:15 pm, arr LHR Thu 10:50 am (Economy V, seat 35F).
```

- [ ] **Step 4: Manual smoke test — stdin**

```bash
cat test-cases/test-case-email-FQZ1B5-popclip-input.txt | uv run python "United Itinerary.popclipext/parse.py"
```

Expected: the 7-line FQZ1B5 output.

- [ ] **Step 5: Manual smoke test — reservation-UI regression**

```bash
uv run python "United Itinerary.popclipext/parse.py" test-cases/test-case-6-popclip-input.txt
```

Expected: output identical to what today's parser produces for that input (no change).

- [ ] **Step 6: Commit**

```bash
git add "United Itinerary.popclipext/parse.py"
git commit -m "feat: add CLI I/O to parse.py (file / stdin / pbpaste / POPCLIP_TEXT)

Consolidates input/output handling into the PopClip bundle script so
it can serve as both the PopClip extension entry point and the CLI
(via an upcoming symlink from summarize-united-itinerary.py).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Replace `summarize-united-itinerary.py` with symlink

**Files:**
- Delete: `summarize-united-itinerary.py` (regular file)
- Create: `summarize-united-itinerary.py` → symlink to `United Itinerary.popclipext/parse.py`

- [ ] **Step 1: Remove the current file**

```bash
cd /Users/felciano/Developer/github.com/felciano/itinerary-parser
rm summarize-united-itinerary.py
```

- [ ] **Step 2: Create relative symlink**

```bash
ln -s "United Itinerary.popclipext/parse.py" summarize-united-itinerary.py
ls -l summarize-united-itinerary.py
```

Expected: `summarize-united-itinerary.py -> United Itinerary.popclipext/parse.py`.

- [ ] **Step 3: Verify the symlink is executable and works**

```bash
./summarize-united-itinerary.py test-cases/test-case-email-NLY82V-popclip-input.txt
```

Expected: same output as Task 11 Step 3 (via the bundle script).

- [ ] **Step 4: Verify full test suite still passes**

```bash
uv run pytest -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A summarize-united-itinerary.py
git commit -m "refactor: symlink summarize-united-itinerary.py to PopClip parse.py

One file, two entry points. Eliminates the 275-line / 417-line drift
between the CLI script and the PopClip bundle script. Both now point
at the same feature-complete source.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

*(`git add -A` handles the delete-and-symlink-create atomically.)*

---

## Task 13: Final verification — manual PopClip install test + cleanup

- [ ] **Step 1: Run the full test suite one more time**

```bash
uv run pytest -v
```

Expected: all PASS.

- [ ] **Step 2: Verify the bundle directory is clean (no stray files)**

```bash
ls -la "United Itinerary.popclipext/"
```

Expected: `Config.json`, `parse.py`, possibly `.DS_Store`. No `__pycache__/` — if present, remove with `rm -rf "United Itinerary.popclipext/__pycache__"` and consider a `.gitignore` entry.

- [ ] **Step 3: Manual PopClip install test**

This is user-driven (cannot be automated). Instruct the user:

> Double-click `United Itinerary.popclipext` in Finder. PopClip should prompt to install or update the extension. After installing, select text from one of the Gmail eTicket emails and confirm the "Parse United Itinerary" action produces the expected summary on the clipboard.

If the user reports failure, inspect PopClip's console output or logs, and re-check that `parse.py` runs standalone via `python "United Itinerary.popclipext/parse.py"` with a file argument.

- [ ] **Step 4: Drop the stash from pre-work (WIP edits superseded)**

```bash
git stash list
git stash drop  # drops the most recent stash — confirm it matches the pre-work entry
```

- [ ] **Step 5: Generate expected output for test-case-6 (optional, nice-to-have)**

The existing `test-case-6-popclip-input.txt` and `test-case-6-input.txt` have no corresponding `test-case-6.yaml`. Generate one to cover the multi-chunk reservation-UI path:

```bash
uv run python "United Itinerary.popclipext/parse.py" test-cases/test-case-6-popclip-input.txt
```

Copy the output into a new `test-cases/test-case-6.yaml`:

```yaml
- description: "Multi-segment reservation UI (PopClip format): 3 legs with 2 connections"
  input_text_block_file: "test-case-6-popclip-input.txt"
  expected_summary: |
    <paste output here, 2-space indented under 'expected_summary: |'>
```

Then add to `tests/test_reservation_ui_snapshot.py` parametrization:

```python
@pytest.mark.parametrize("fixture_file", [
    "test-case-1.yaml",
    "test-case-2.yaml",
    "test-case-3.yaml",
    "test-case-4.yaml",
    "test-case-5.yaml",
    "test-case-6.yaml",
])
```

And update the test body to handle `input_text_block_file`:

```python
def test_reservation_ui_output_matches_fixture(fixture_file: str) -> None:
    case = load_yaml_case(fixture_file)  # conftest already resolves the file ref
    result = parser.parse_united_itinerary(case["input_text_block"])
    expected = case["expected_summary"].rstrip("\n")
    assert result.rstrip("\n") == expected
```

Re-run tests:

```bash
uv run pytest -v
```

Expected: the new fixture passes.

- [ ] **Step 6: Final commit**

```bash
git add test-cases/test-case-6.yaml tests/test_reservation_ui_snapshot.py
git commit -m "test: add test-case-6 fixture covering multi-leg reservation UI

Generated from the already-present test-case-6-popclip-input.txt and
pinned to current output. Extends the snapshot safety net.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-review checklist (already executed; notes here for the implementer)

- **Spec coverage:** every section of the design spec maps to at least one
  task. Data model → Task 3. Chunk grouping → Task 4. Format detection →
  Task 5. Email parser → Tasks 6–8. Renderer → Task 9. Dispatch + fixtures
  → Task 10. CLI I/O + symlink → Tasks 11–12. PopClip installability →
  verified in Task 13.
- **Placeholder scan:** no TBD / TODO / "implement later" in any task body.
- **Type consistency:** function/field names match between data-model task
  and consumer tasks (`dep_datetime`, `arr_datetime`, `fare_class`, `seat`,
  `confirmation_number`, `accrual_award_miles`, `upgrade_fees`).
- **Byte-equal output for reservation UI:** guarded by the snapshot tests
  created in Task 2, which run on every subsequent change.
- **PopClip bundle is self-contained:** all parser code stays in
  `United Itinerary.popclipext/parse.py`. Tests live outside the bundle.
  Dev deps (pytest, pyyaml) are `dependency-groups` entries — never imported
  by `parse.py` itself.
