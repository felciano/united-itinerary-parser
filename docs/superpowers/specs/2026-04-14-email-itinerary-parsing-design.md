# Email Itinerary Parsing — Design Spec

**Date:** 2026-04-14
**Status:** Approved — proceeding to implementation

## Goal

Extend the existing United Airlines itinerary parser to handle United eTicket
Itinerary and Receipt emails (`Subject: eTicket Itinerary and Receipt for
Confirmation XXXXXX`, `From: Receipts@united.com`) in addition to the current
reservation-UI text.

Primary workflow: user selects the email body in Gmail → PopClip → parser
produces a concise summary on the clipboard. Future-compatible with a planned
Claude Cowork path that ingests incoming emails and creates calendar events.

## Non-goals

- Forwarded `.eml` / MIME parsing. We parse what lands in the clipboard from a
  browser copy.
- Timezone math. Times stay as naive local times at each airport.
- Gmail-API ingestion. The parser remains text-in / text-out; Cowork
  automation is out of scope for this work.
- Reworking the existing reservation-UI output format. It stays untouched.

## Input format (email)

After rendering + copy-paste from Gmail, the body arrives as plain text with
tab-separated columns preserved from the source HTML tables. Observed
structure (from real samples `FQZ1B5`, `NLY82V`):

```
Thank you for choosing United.
...
Confirmation Number:
<CONFCODE>
Flight N of M UA<num>		Class: United <name> (<code>)
<Weekday>, <Mon DD, YYYY>		<Weekday>, <Mon DD, YYYY>
HH:MM AM/PM		HH:MM AM/PM
<City, Region/Country (IATA)>		<City, Region/Country (IATA)>
... [Flight block repeats] ...
Traveler Details
<PASSENGER NAME>
eTicket number: <number>	Seats: <IATA>-<IATA> <SEAT>
Frequent Flyer: ...	<IATA>-<IATA> <SEAT>
...additional seat rows, one per segment...
Purchase Summary
Method of payment:	<method>
Date of purchase:	<date>
Airfare:	<amount>
...tax lines...
Total Per Passenger:	<amount> USD
Total:	<amount> USD
[Optional: Additional Purchase Summary blocks for upgrade fees]
Fare Rules
MileagePlus Accrual Details
Ramon Felciano
Date	Flight	From/To	Award Miles	PQP	PQF
...one row per segment...
MileagePlus accrual totals:	<miles>	<pqp>	<pqf>
[Legal boilerplate — ignored]
```

Key differences vs reservation-UI input:

- All segments flat (`Flight 1 of 4`, `Flight 2 of 4`, …). No nested
  `Connection N of M` markers.
- No aircraft type, no pre-computed duration, no "Nonstop / N stop" label.
- New fields: confirmation number, eTicket number, seat assignments, fare
  class, upgrade fees, MileagePlus accrual totals.

## Output format (email source)

Three-level nested list: itinerary → trip chunk → segment. Chunk headers
include city names; segment lines stay terse with IATA codes.

Example (FQZ1B5):

```
- Itinerary FQZ1B5: $2,564.60 + $1,100.00 upgrades (eTicket 0162389632983). Accrual: 21,510 miles / 2,151 PQP / 4 PQF.
  - London (LHR) to Punta Cana (PUJ) (via Newark (EWR)):
    - LHR > EWR UA 17:   dep LHR Sun Apr 26, 10:25 am, arr EWR 1:20 pm (Economy W, seat 33K).
    - EWR > PUJ UA 1514: dep EWR Mon Apr 27, 8:11 am, arr PUJ 12:15 pm (Economy W, seat 09D).
  - Punta Cana (PUJ) to London (LHR) (via Houston (IAH)):
    - PUJ > IAH UA 524:  dep PUJ Thu Apr 30, 2:20 pm, arr IAH 6:04 pm (Economy S, seat 09D).
    - IAH > LHR UA 5:    dep IAH Thu Apr 30, 8:05 pm, arr LHR Fri 11:35 am (Economy S, seat 32G).
```

Single-segment nonstop example (NLY82V):

```
- Itinerary NLY82V: $556.50 (eTicket 0162379511080). Accrual: 4,707 miles / 523 PQP / 1 PQF.
  - Washington (IAD) to London (LHR):
    - IAD > LHR UA 924: dep IAD Wed Mar 11, 11:15 pm, arr LHR Thu 10:50 am (Economy V, seat 35F).
```

Rules:

- **Itinerary header**: `- Itinerary <confcode>: <total> [+ <upgrades> upgrades] (eTicket <eticket>). Accrual: <miles> miles / <pqp> PQP / <pqf> PQF.`
  - Missing pieces drop silently (e.g., `Accrual: …` omitted if not present).
- **Chunk header**: `- <DepCity> (<DEP>) to <ArrCity> (<ARR>)[ (via <ViaCity> (<VIA>)[, <ViaCity2> (<VIA2>)])]:`
  - `<DepCity>` is the text before the first comma in the email's city label
    (`"Newark, NJ/New York, NY, US (EWR)"` → `Newark`). `"Newark/New York (EWR)"`
    is intentionally *not* emitted — we pick the first name and move on.
  - `(via …)` is omitted for single-segment chunks.
- **Segment line**: `  - <DEP> > <ARR> UA <num>: dep <DEP> <Wkd> <Mon> <D>, <h:mm am/pm>, arr <ARR>[ <Wkd>] <h:mm am/pm> (<FareClass>, seat <seat>).`
  - Arrival weekday token appears only when the arrival date differs from the
    departure date.

## Chunk-grouping rule

Walk segments in order. Segments N and N+1 belong to the same chunk iff:

1. `segments[N].arr_airport == segments[N+1].dep_airport`, AND
2. Time gap between `segments[N].arr_datetime` and `segments[N+1].dep_datetime`
   is ≤ 24 hours.

Otherwise N+1 starts a new chunk. Matches the IATA industry convention for
connection-vs-stopover.

## Architecture

### File layout

```
United Itinerary.popclipext/
├── Config.json
└── parse.py                     # Single source of truth (parser + CLI)

summarize-united-itinerary.py    # Symlink → United Itinerary.popclipext/parse.py

summarize-united-itinerary.js    # Unchanged (Drafts port)

test-cases/
├── test-case-1.yaml … test-case-5.yaml   # Existing reservation-UI fixtures
├── test-case-6-input.txt                 # Existing (reservation-UI, no expected yet)
├── test-case-6-popclip-input.txt         # Existing
├── test-case-email-FQZ1B5-popclip-input.txt   # New email sample
├── test-case-email-NLY82V-popclip-input.txt   # New email sample
└── test-case-email-*.yaml                     # New: wraps inputs + expected output
```

### Module organization inside `parse.py`

```
parse.py
├── Data model              # @dataclass Segment, Chunk, Itinerary
├── Format detection        # detect_format(text) -> "reservation_ui" | "email"
├── Reservation UI parser   # parse_reservation_ui(text) -> Itinerary
│                           # (existing two-variant logic refactored to build Itinerary)
├── Email parser            # parse_email(text) -> Itinerary   (NEW)
├── Chunk grouping          # group_into_chunks(segments) -> list[Chunk]
├── Renderer                # render(itinerary) -> str
├── I/O helpers             # get_input, output_result (file / stdin / pbpaste / POPCLIP_TEXT)
└── main()                  # detect → parse → group → render → output
```

Constraints:

- Standard library only (no pip deps). `dataclasses`, `datetime`, `decimal`,
  `re`, `enum`, `subprocess`. PopClip `.popclipext` bundles install as-is;
  external imports break installation.
- All code in one file so the bundle is self-contained.
- Type hints throughout. Functions ≤ 30 lines where practical.

## Data model

```python
@dataclass
class Segment:
    flight_number: str              # "17" or "921/1514" (reservation-UI condensed form)
    dep_airport: str                # "LHR"
    dep_city: Optional[str]         # "London" (emails); None for reservation UI
    arr_airport: str
    arr_city: Optional[str]
    dep_datetime: datetime          # naive local time
    arr_datetime: datetime          # naive local time
    fare_class: Optional[str]       # "Economy W" (emails only)
    seat: Optional[str]             # "33K" (emails only)
    aircraft: Optional[str]         # "Boeing 777-200ER" (reservation UI only)
    duration: Optional[timedelta]   # pre-computed (reservation UI) or None

@dataclass
class Chunk:
    segments: list[Segment]
    # Derived at render time: origin, destination, via list

@dataclass
class Itinerary:
    source: str                     # "reservation_ui" | "email"
    chunks: list[Chunk]
    total_cost: Optional[Decimal]
    miles: Optional[int]            # reservation-UI upgrade miles
    plus_points: Optional[int]      # reservation UI only
    confirmation_number: Optional[str]
    eticket_number: Optional[str]
    upgrade_fees: Optional[Decimal] # sum of "Additional Purchase Summary" totals
    accrual_award_miles: Optional[int]
    accrual_pqp: Optional[int]
    accrual_pqf: Optional[int]
```

## Format detection

Positive signatures (all-lines-in-body):

- **Email**: presence of `Thank you for choosing United` AND `Confirmation Number:`.
- **Reservation UI**: presence of `Flight selection list` OR `Duration:` OR `Aircraft type:`.

If both match, email wins (conservative — email signatures are less likely to
appear coincidentally). If neither matches, fall back to the existing
reservation-UI parser behavior (no format found → empty output).

## Email parser specifics

1. **Segment split**: reuse existing `_split_sections` on `Flight N of M` marker.
2. **Per segment**:
   - Header regex: `Flight \d+ of \d+ UA(\d+)\s+Class: (.+?) \(([A-Z]+)\)`
     — captures flight number, fare class name, fare class code (code is 1-2
     uppercase letters; observed values include `W`, `S`, `V`, `PZ`).
     `fare_class` normalized as `"<Name> <Code>"` with the leading `United `
     prefix stripped for compactness (e.g. `"United Polaris business (PZ)"` →
     `"Polaris business PZ"`).
   - Dates line (tab-split): `Weekday, Mon DD, YYYY` twice.
   - Times line (tab-split): `HH:MM AM/PM` twice.
   - Cities line (tab-split): `City[, subregion], Country (IATA)` twice.
     Extract city as text up to first comma.
3. **Seats**: `Seats: IATA-IATA <seat>` for first segment; subsequent rows are
   bare `IATA-IATA <seat>`. Match segments by airport pair.
4. **Money**: `Total:\s+([\d,]+\.\d{2})\s+USD` — take the first occurrence as
   base total; sum subsequent `Additional Purchase Summary` `Total:` lines into
   `upgrade_fees`.
5. **Accrual**: parse the `MileagePlus accrual totals:` row for award miles /
   PQP / PQF.
6. **Confirmation / eTicket**: regex anchored on the `Confirmation Number:`
   and `eTicket number:` labels.

### Date-change detection

`arr_datetime` date differs from `dep_datetime` date — no heuristic needed;
the email gives us both dates explicitly.

### Unknown / missing fields

Follow existing parser convention: emit `???` placeholders rather than
failing. Concretely, if a flight header parses but its dates/times don't,
render the segment line with `???` in the missing slots. Don't drop segments.

## Renderer

`render(itinerary) -> str` is the inverse of parsing: pure function from
`Itinerary` to text.

For `source == "reservation_ui"`: preserve the existing output format as
closely as possible (flat segments under `- Itinerary:` header). The existing
behavior is the spec; we're refactoring the parser layer underneath, not the
output.

For `source == "email"`: use the nested format from the Output section above.

## Testing

- **Fixture format**: YAML, matching existing `test-cases/*.yaml` shape
  (`description`, `input_text_block`, `expected_summary`).
- **New fixtures** (initially 2, add more as needed):
  - `test-case-email-FQZ1B5.yaml` — multi-segment round trip, upgrade fees, accrual.
  - `test-case-email-NLY82V.yaml` — single-segment nonstop.
- **Test runner**: `pytest` via `uv run pytest`.
  - `test_parse_email.py` — parameterized over email YAML fixtures; loads
    `input_text_block`, runs full pipeline, asserts `expected_summary` matches.
  - `test_parse_reservation_ui.py` — parameterized over existing YAML
    fixtures; guards the refactor (output must stay byte-identical where the
    fixtures define expected output).
  - `test_chunk_grouping.py` — direct unit tests of `group_into_chunks`:
    empty list, single segment, two segments with arr==dep and gap <24h,
    two segments with arr==dep and gap >24h, two segments with arr!=dep.
  - `test_detect_format.py` — straightforward classifier tests.
- `pyproject.toml` gains a `[dependency-groups]` with `pytest` via
  `uv add --dev pytest` (dev-only; no runtime deps added, the bundle stays
  pure-stdlib).

## Error handling

Existing convention stands: the parser does not raise on missing fields; it
emits `???` or omits optional lines. The CLI exits non-zero only if no input
is provided or no itinerary is detected at all — same as today.

## PopClip installability

The bundle folder `United Itinerary.popclipext/` remains self-contained. All
parsing code lives in `parse.py` inside it. `Config.json` is unchanged.
`summarize-united-itinerary.py` at repo root is a symlink to
`United Itinerary.popclipext/parse.py` so both CLI and PopClip workflows use
the same code.

Install test: double-clicking `United Itinerary.popclipext` in Finder should
still install the extension and the "Parse United Itinerary" action should
still work.

## Migration notes

- The existing reservation-UI `parse.py` already contains two variants
  (`parse_popclip_format` for bullet-separated text, `parse_original_format`
  for markdown) plus a dispatcher. Both variants stay — the refactor moves
  them behind an `Itinerary`-producing interface, but their regex logic is
  preserved.
- The existing CLI `summarize-united-itinerary.py` (275 lines) is missing the
  bullet-format support that `parse.py` has — replacing it with a symlink is
  a strict improvement.
- `summarize-united-itinerary.js` (Drafts port) is not touched; it's a
  separate execution environment and stays on the old format.
