# AGENTS.md

Universal project context for any coding agent working in this repository.

## Commands

```bash
uv run pytest                              # full suite (152 tests)
uv run pytest tests/test_gf_parse.py -v    # one file
uv run pytest -k "infer_year" -v           # one test by name
uv run ruff format .                       # format
```

Run the parser directly:

```bash
./summarize-united-itinerary.py test-cases/test-case-gf-5-input.txt   # file
cat itinerary.txt | ./summarize-united-itinerary.py                   # stdin
./summarize-united-itinerary.py                                       # clipboard (pbpaste/pbcopy)
```

Reproduce a PopClip invocation, which is the only path that matters for the
extension — it uses the system interpreter, no virtualenv, no stdin:

```bash
env -i HOME="$HOME" PATH="/usr/bin:/bin" \
  POPCLIP_TEXT="$(cat test-cases/test-case-gf-5-input.txt)" \
  /bin/sh "United Itinerary.popclipext/run.sh" </dev/null
```

## Hard constraint

`United Itinerary.popclipext/parse.py` must stay **one file importing only the
standard library**. PopClip is not the only caller — other macOS utilities shell
out to it as a bare `python3 parse.py` against the system interpreter (3.9.6),
with no virtualenv and no install step. Never split it into modules; it is
~1,200 lines and uses section banners instead. Never add a runtime dependency.
`pytest` and `PyYAML` are dev-only and must never be imported by `parse.py`.

`summarize-united-itinerary.py` is a **symlink** to `parse.py`. Because
`sys.path[0]` follows the symlink's directory rather than the target's, sibling
imports would break even if the single-file rule were relaxed.

## Architecture

One entry point, `parse_united_itinerary(text, reference_date=None)`, classifies
the input with `detect_format()` and dispatches to one of three paths. It returns
`""` when nothing parses, and `main()` turns that into exit 1.

| Source | Detected by | Path |
|---|---|---|
| Google Flights | `Travel time:` + `kg CO2e` | `parse_google_flights` → `render_google_flights` |
| United eTicket email | `Thank you for choosing United` + `Confirmation Number:` | `parse_email` → `render_email` |
| United.com reservation UI | `Flight selection list` / `Aircraft type:` / `Duration:` | `parse_popclip_format` or `parse_original_format` |

Google Flights is checked first. The three signature sets don't overlap; tests
assert the existing two still classify correctly.

**Two generations of code coexist.** The Google Flights and email paths parse
into `Itinerary` → `Chunk` → `Segment` dataclasses and render from them. The
reservation-UI path is older and builds output strings directly, never touching
the dataclasses — which is why `parse_united_itinerary` reads `_SOURCE_LABEL` by
literal key for its header. Don't assume the dataclasses are involved when
working on that path.

Renderers share `_render_segment_line(seg, extras)`; the per-format wrappers
differ only in their parenthetical extras (email: fare class + seat; Google
Flights: cabin + aircraft). `seg.airline or "UA"` keeps United output unchanged
because those parsers never set `airline`.

### The header line

Every format leads with route, dates, then cost, and **no trailing period**:

```
- Google Flights itinerary: LHR <-> BIQ, Wed Aug 26 - Sun Aug 30, £400 round trip
- United.com itinerary: LHR > PUJ > SFO > LHR, Sat Apr 25 - Sun May 3, $3,248 + 62,500 miles
```

`_summarize_route` collapses a there-and-back trip to `<->` and chains anything
else with `>`, so a three-chunk trip ending where it started is not mistaken for
a round trip. Dates bound the first and last chunk *departures*, collapsing to a
single date when they coincide.

The reservation-UI path has no dataclasses to summarise, so
`_summarize_reservation_ui` reads route and dates back out of the lines that
path already emitted. That is parsing our own output, done deliberately:
reworking those two ~120-line functions would risk the six byte-exact snapshots
guarding them, and the format is ours and fixed.

### Google Flights specifics

Google Flights has **more than one layout**, and each new one has broken
parsing in a different way. Two are handled:

- **Search results** — slices headed `Departure`/`Return`, a price per slice,
  and the airline block concatenated onto one line.
- **Selected trip** — slices headed `Departing flight`/`Returning flight`, the
  airline block split across three lines (`_join_gf_flight_rows` rejoins any
  line that is nothing but a cabin word), and no per-slice fare. The total sits
  in a preamble above the first slice, which `_gf_preamble` recovers and which
  is consulted only for what the slices did not supply.

Expect further layouts (multi-city, mixed cabins). An unrecognised one yields
no output rather than wrong output, and each needs a capture pair — see Tests.


Parsing anchors on a handful of line shapes and **ignores everything else by not
matching**. Google interleaves a lot of varying noise (legroom, Wi-Fi, emissions,
contrail warming, delay warnings, "Avoids as much CO2e as N trees…"). A filter
that enumerated noise would break on each new paste; structural anchoring hasn't.

Four things are easy to get wrong:

- **Times are local and arrivals are never derived.** A leg can arrive at a clock
  time earlier than departure plus its stated duration. Take the printed time
  plus the printed `+N` marker, nothing else.
- **`+N` counts from the slice's base date**, not cumulatively. Three segments
  across two layovers can all read `+1`.
- **`group_into_chunks` is not used here.** Its 24-hour rule would split a longer
  layover, and cross-timezone gap arithmetic is meaningless. Each slice becomes
  one `Chunk`.
- **Splitting a run-on number is guesswork.** In `Wed, Aug 26171 kg CO2e`
  nothing marks where day 26 ends and 171 kg begins, so the date matcher
  tolerates trailing junk instead, falling back to a single-digit day when a
  greedy two-digit read exceeds 31. Two earlier attempts to split there each
  swallowed a digit.

Two regex traps, both of which shipped as bugs first:

- A **zero-width lookahead splits at every match**, so `(?=\d{1,2}:\d{2})`
  fires at both `11:45` and `1:45` and halves the hour. Consume the match
  instead.
- **`re.IGNORECASE` makes `[a-z]` match uppercase.** A guard like
  `(?![a-z])` after `round trip` then rejects the `E` of `Economy` and matches
  nothing. Scope the flag with `(?i:…)`.

Google omits the year, so `_infer_year` recovers it from the printed weekday.
The search window is **12 years, not 7** — a date returns to the same weekday on
an irregular cycle, and Wed Aug 26 gaps from 2026 to 2037.

Chunk-header place names resolve in three tiers: the curated `_IATA_CITY` map,
then a city harvested from any layover line in the same paste, then the airport
name minus a trailing `Airport`. The map is a deliberate exception list, not an
attempt at coverage — LHR is absent because `Heathrow` beats `London`.

### PopClip capture is not the clipboard

`_normalize_gf_flattened` exists because PopClip reads selections through the
macOS accessibility API, which flattens a Google Flights result card onto **one
line**: row breaks vanish, fields join with `·` (U+00B7), spaces become U+00A0,
and images leave U+FFFC. Every anchor is line-anchored, so without normalisation
nothing matches.

A clipboard copy of the same selection is properly line broken, **so this failure
mode is invisible to any test written from a paste** — and text pasted through a
chat window is normalised further still. When debugging the extension, capture
PopClip's real input (`run.sh` writes it to `/tmp/popclip-united-text.txt`)
rather than testing a pasted copy.

## Tests

Fixtures live in `test-cases/` as YAML with either an inline `input_text_block`
or an `input_text_block_file` pointing at a sibling `.txt`. `tests/conftest.py`
normalises tab indentation in the older fixtures.

Google Flights tests **pin `reference_date=date(2026, 8, 2)`**. Without it the
inferred year tracks the wall clock and fixtures rot.

**Capture pairs.** For each Google Flights layout, keep two fixtures of the
*same* trip — one copied to the clipboard, one taken from PopClip — plus a test
asserting they render identically. `test_gf_roundtrip.py` is the model. A
clipboard-only fixture cannot see the accessibility-API flattening, which is
exactly how that bug reached a user.

`test-case-gf-popclip-flattened-input.txt` is a byte-exact PopClip capture; a
guard test asserts it stays single-line, since a fixture that gains newlines
silently stops testing what it exists for.

Expected-output strings and YAML fixture lines are **data** — exempt from the
88-character limit, and never reflow them.

## Working on the PopClip extension

PopClip does **not** execute the folder in
`~/Library/Application Support/PopClip/Extensions/`. It stores extensions in
`~/Library/Application Support/PopClip/Data/PopClip.sqlite` (CloudKit-synced) and
materialises them into a runtime cache per invocation. Editing either location
has no effect — both get overwritten from the database.

- `Config.json` points at `run.sh`, not `parse.py`. PopClip runs a script under
  `/bin/sh` unless the extension declares `popclip version` ≥ 4035 or an explicit
  `interpreter`; a `.sh` launcher makes that unambiguous, finds a Python itself,
  and reports failures on the clipboard instead of a bare "X".
- **Installing stacks duplicates** rather than replacing, and PopClip executes the
  oldest. Always remove the extension in PopClip → Settings → Extensions and
  relaunch before installing.
- **Double-clicking a package moves it to the Trash.** Never double-click one
  inside the repo; build to `dist/` or the Desktop.

Deploy: remove in Settings → relaunch PopClip → double-click a `.popclipextz`
built outside the repo → run the action.

## Work queue

`TODO.md` holds deferred findings, each with the reasoning that made it safe to
leave. Check it before starting work in an area it touches.

## Docs

`docs/superpowers/specs/` holds design specs and `docs/superpowers/plans/` the
task-by-task implementation plans, both dated. The Google Flights spec
(`2026-08-02-google-flights-parsing-design.md`) records the rationale behind the
decisions above.
