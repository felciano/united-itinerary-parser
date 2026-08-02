# Google Flights Itinerary Parsing — Design

**Date:** 2026-08-02
**Status:** Approved for planning

## Goal

Extend the parser to recognize itineraries copied from the Google Flights web
UI, in addition to the two United sources it already handles. Add a source
attribution to the rendered output of all three formats, and drop decimal
places from all rendered prices.

## Hard constraints

`United Itinerary.popclipext/parse.py` must remain **a single file importing
only the Python standard library**. PopClip is not the only caller — other
macOS utilities shell out to it directly, so it has to run as a bare
`python3 parse.py` against the system interpreter with no virtualenv and no
install step. The file will grow past 1,000 lines; use section banners rather
than splitting it. `pytest` and `PyYAML` stay dev-only in
`[dependency-groups]` and are never imported by `parse.py`.

`summarize-united-itinerary.py` is a symlink to `parse.py`, so `sys.path[0]`
resolves to the repo root rather than the bundle directory. Sibling imports
would break even if the single-file rule were relaxed.

## Input format

Google Flights paste is line-oriented, with adjacent field values concatenated
without separators. Seven line shapes carry all the signal. Everything else is
ignored by not matching any anchor. This is deliberate rather than incidental:
the noise varies widely across pastes and new varieties keep appearing.
Observed so far — legroom, Wi-Fi (both `Wi-Fi for a fee` and `Free Wi-Fi`),
in-seat power and USB, on-demand video, `Stream media to your device`,
contrail warming, emissions estimates, baggage and fare conditions,
`Often delayed by 30+ min`, `Plane and crew by ANA Wings`, and prose such as
`Avoids as much CO2e as 791 trees absorb in a day`. Blank lines may or may not
separate segments. A filtering approach that enumerated noise would have
broken on each new paste; anchoring on structure has not.

| Anchor | Example | Yields |
|---|---|---|
| Slice header | a line that is exactly `Departure` or `Return` | chunk boundary |
| Slice date | `Wed, Aug 26` | weekday, month, day (no year) |
| Price | `£251` then `round trip` on the next line | currency symbol, amount, trip type |
| Time + airport | `5:15 PM+1Haneda Airport (HND)` | local time, day offset, airport name, IATA |
| Travel time | `Travel time: 14 hr 15 minOvernight` | segment separator (value not stored) |
| Airline / cabin / aircraft / flight | `SWISSEconomyAirbus A220-300 PassengerLX 355` | `LX`, `355`, `Economy`, `Airbus A220-300` |
| Layover | `10 hr 35 min layoverRome (FCO)Long layover` | segment separator, and a city name for that IATA code |

The airline line is parsed with one regex anchored at both ends: non-greedy
airline name, then a cabin from `Premium economy|Economy|Business|First`
(longest alternative first, so `Premium economy` is not shadowed by
`Economy`), then aircraft, then a `XX NNN` flight designator at end of line.
A trailing ` Passenger` is stripped from the aircraft, so
`Airbus A220-300 Passenger` becomes `Airbus A220-300` while `Boeing 777` is
left alone.

The price line's trailing word (`round trip` / `one way`) describes the fare,
not the paste. A departure-only paste of a round-trip search still says
`round trip`. Mirror whatever text is present; omit the phrase if absent.

### Local times cannot be arithmetic-derived

Example 3's `LIN 3:05 PM → LCY 3:55 PM` covers a stated 1 hr 50 min of travel,
because Milan and London are an hour apart. Arrival datetimes must therefore
come from the printed local time plus the printed `+N` marker, never from
adding the travel time to the departure.

The `+N` offset counts from the slice's base date, not cumulatively from the
previous segment. The STN→HND sample settles this: base date `Wed, Aug 26`,
then a 14 hr 15 min layover carries `12:10 PM` into `2:25 AM+1`, and every
subsequent time — `7:05 PM+1`, `9:00 PM+1`, `10:20 PM+1` — stays at `+1`
rather than accumulating, even across a second layover. All of them are
Aug 27.

This is also why `group_into_chunks` must not be used for this format. Its
24-hour rule would misgroup a layover longer than a day, and cross-timezone
gap arithmetic is not meaningful here. Google Flights states the boundaries
explicitly, so each `Departure` / `Return` slice maps directly to one `Chunk`.

### Year inference

The input carries no year but does carry a weekday. `_infer_year(month, day,
weekday, reference)` searches forward from a reference date for the first
matching date whose weekday agrees, capped at seven years, falling back to the
reference year when nothing matches. The reference is an injectable parameter
defaulting to `date.today()`, so tests pin it and stay deterministic.

For a round trip, the Return slice resolves forward from the Departure date
rather than from today, which handles a December-to-January crossing.

### Place names

Chunk headers resolve each airport's label in this order:

1. A literal `_IATA_CITY` dict in `parse.py`.
2. The city name from a layover line for that IATA code, anywhere in the same
   paste.
3. The airport name with a trailing ` Airport` stripped.

The dict is a **curated exception list**, not a derived rule. It holds only
those airports whose Google Flights name reads poorly as a label and which the
paste gives no other way to name, and it is extended by hand as cases surface:

```python
_IATA_CITY = {
    "HND": "Tokyo",   # "Haneda Airport"
    "FCO": "Rome",    # "Leonardo da Vinci International Airport"
}
```

LHR is deliberately absent. `Heathrow` reads better than `London`, and on a
London round trip out of LHR and back into LCY, mapping both to `London` would
collapse the distinction between the endpoints.

Tier 2 keeps the map small. `Kansai International Airport (KIX)` strips to
`Kansai International`, but the same paste carries `1 hr 55 min layoverOsaka
(KIX)`, so it resolves to `Osaka` with no map entry. The map only has to grow
for airports that are awkwardly named *and* never appear as a layover.

The tradeoff is that an unmapped airport can read differently across pastes
depending on its role — LIN as `Milan` where it is a stop, `Milan Linate`
where it is an endpoint. Adding a map entry pins it. This is accepted:
self-healing on the airports that actually bother you beats maintaining
coverage up front.

Resulting labels:

| IATA | Google Flights name | Renders as | Tier |
|---|---|---|---|
| LHR | Heathrow Airport | `Heathrow` | stripped |
| STN | London Stansted Airport | `London Stansted` | stripped |
| GVA | Geneva Airport | `Geneva` | stripped |
| BIQ | Biarritz Airport | `Biarritz` | stripped |
| LCY | London City Airport | `London City` | stripped |
| IST | Istanbul Airport | `Istanbul` | stripped (layover agrees) |
| LIN | Milan Linate Airport | `Milan` / `Milan Linate` | layover / stripped |
| KIX | Kansai International Airport | `Osaka` | layover |
| HND | Haneda Airport | `Tokyo` | map |
| FCO | Leonardo da Vinci International Airport | `Rome` | map |

This resolution applies to the Google Flights path only. The email and
reservation-UI sources already carry usable city names, and routing them
through the map would churn their fixtures for no gain.

## Changes affecting all three formats

### Source attribution

`Itinerary.source` already exists (`"reservation_ui"` | `"email"`) and gains
`"google_flights"`. A module-level map drives the rendered label:

```python
_SOURCE_LABEL = {
    "reservation_ui": "United.com",
    "email": "United.com",
    "google_flights": "Google Flights",
}
```

It appears as a leading qualifier on the itinerary header line:

- `- United.com itinerary: $3,248 + 62,500 miles`
- `- United.com itinerary NLY82V: $557 (eTicket 0162379511080). …`
- `- Google Flights itinerary: £251 round trip.`

The eTicket email is labelled `United.com` even though it arrives by email.
Two labels was the explicit request.

Two construction sites change, both one-liners: `parse.py:344` in the
dataclass-based email renderer, and `parse.py:788` in the legacy
reservation-UI path. That legacy path builds its header as a raw string rather
than going through `Itinerary`, so it reads the map by literal key. Converting
it to use the dataclass is a refactor this feature does not need.

### Prices lose their decimals

All rendered prices drop to whole currency units, rounded half-up, across
every source and currency. `$3,248.25` becomes `$3,248`; `$556.50` becomes
`$557`; `$2,564.60 + $1,100.00 upgrades` becomes `$2,565 + $1,100 upgrades`.
`_fmt_money` takes a currency symbol and formats with `,.0f` after quantizing
with `ROUND_HALF_UP`.

The reservation-UI path currently interpolates the regex match as a raw
string, so it must parse to `Decimal` and reformat rather than passing the
captured text through.

## Data model deltas

Small, and deliberately additive:

- `Segment.airline: Optional[str]` — the two-letter code, e.g. `"LX"`.
- `Itinerary.currency: str = "$"`.
- `Itinerary.trip_type: Optional[str]` — mirrored `"round trip"` / `"one way"`.

Cabin reuses the existing `fare_class` field; `"Economy"` renders identically
to the email path's `"Economy V"`. Aircraft reuses the existing `aircraft`
field. No new dataclass, and segment travel time is not stored, since nothing
renders it.

## New and modified functions

New: `_parse_gf_slices`, `_parse_gf_segments`, `_infer_year`,
`parse_google_flights`, `render_google_flights`,
`_render_itinerary_header_google_flights`.

Modified:

- `detect_format` gains a `"google_flights"` branch, checked first, keyed on
  the co-occurrence of `Travel time:` and `kg CO2e`. No overlap with the
  existing signatures (`Duration:`, `Aircraft type:`, `Flight selection list`,
  `Thank you for choosing United`), so the two existing paths are untouched.
- `_render_segment_line_email` splits into a shared `_render_segment_line(seg,
  extras)` core plus per-format extras lists. Email passes fare class and
  seat; Google Flights passes cabin and aircraft. The hardcoded `"UA"` becomes
  `seg.airline or "UA"`, which preserves email and reservation-UI output.
- `_render_chunk_header_email` is reused unchanged.
- `parse_united_itinerary` dispatches the new format before its existing
  email check.

## Rendered output

Example 1 (one stop):

```
- Google Flights itinerary: £301 round trip.
  - Heathrow (LHR) to Biarritz (BIQ) (via Geneva (GVA)):
    - LHR > GVA LX 355: dep LHR Wed Aug 26, 2:25 pm, arr GVA 5:05 pm (Economy, Airbus A220-300).
    - GVA > BIQ LX 2332: dep GVA Wed Aug 26, 6:30 pm, arr BIQ 7:50 pm (Economy, Airbus A220-300).
```

Example 2 (nonstop, overnight, crosses midnight):

```
- Google Flights itinerary: £1,497 round trip.
  - Heathrow (LHR) to Tokyo (HND):
    - LHR > HND NH 212: dep LHR Wed Aug 26, 7:00 pm, arr HND Thu 5:15 pm (Economy, Boeing 777).
```

Example 3 (a `Return` slice, two stops, `+1` rollovers, timezone-crossing
final leg):

```
- Google Flights itinerary: £1,355 round trip.
  - Tokyo (HND) to London City (LCY) (via Rome (FCO), Milan Linate (LIN)):
    - HND > FCO AZ 793: dep HND Sun Aug 30, 12:40 pm, arr FCO 8:25 pm (Economy, Airbus A350).
    - FCO > LIN AZ 2010: dep FCO Mon Aug 31, 7:00 am, arr LIN 8:10 am (Economy, Airbus A220-300).
    - LIN > LCY AZ 238: dep LIN Mon Aug 31, 3:05 pm, arr LCY 3:55 pm (Economy, Airbus A220-100).
```

Example 5 (two stops, mixed airlines, blank-line separators, `+1` held flat
across two layovers, and a layover-sourced city name at KIX):

```
- Google Flights itinerary: £1,387 round trip.
  - London Stansted (STN) to Tokyo (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737).
```

Arrival carries a weekday prefix only when it falls on a different date from
departure, matching existing email behaviour. Example 2 is the only sample
that triggers it.

## Round-trip handling

A paste containing both a `Departure` and a `Return` block yields one
`Itinerary` with two chunks. The price rule is tolerant of either observed
behaviour: render once if both blocks state the same amount, otherwise take
the last block's amount, since that reflects the fully selected combination.

No genuine two-block paste was available when this spec was written. Five
samples were supplied and every one of them is a single slice — four
`Departure`, one `Return` — even though the round-trip search context is
visible in the `round trip` price label. It may be that the Google Flights UI
never puts both halves in one copyable region.

The parser stays tolerant of multiple slices regardless, because the splitter
handles N slices at no extra cost, and the round-trip fixture is synthesized
by concatenating the Example 2 and Example 3 blocks. That pairing is
structurally faithful (LHR→HND outbound, HND→LCY return) and exercises the
differing-price branch. It is labelled synthetic in the fixture file. If a
real two-block paste turns up it replaces the fixture with no parser change;
if it turns out none exists, the tolerance costs nothing.

## Testing

Unit tests, all with a pinned reference date where dates are involved:

- One per anchor regex, including the concatenated airline line, the `+N`
  marker, `Premium economy` versus `Economy`, and the ` Passenger` strip.
- `_infer_year` across a weekday match, a year rollover, and the no-match
  fallback.
- Place-name resolution on all three tiers: a mapped airport (HND, FCO), a
  layover-sourced one (KIX to `Osaka`), and an unmapped non-layover falling
  through to the stripped name, including LHR rendering as `Heathrow` rather
  than `London`.
- `+N` held flat across two layovers in the STN→HND sample, asserting the
  third segment lands on Aug 27 rather than Aug 28.
- `detect_format` returning `"google_flights"` for all five Google samples and
  the existing values for the existing fixtures.

End-to-end YAML fixtures following the existing `input_text_block_file`
convention, one per supplied sample plus the synthesized round trip:

| Fixture | Sample | Covers |
|---|---|---|
| `test-case-gf-1` | LHR→BIQ via GVA | one stop, single airline |
| `test-case-gf-2` | LHR→HND nonstop | nonstop, overnight, arrival weekday prefix |
| `test-case-gf-3` | HND→LCY via FCO, LIN | a `Return` slice, timezone-crossing final leg |
| `test-case-gf-4` | LHR→FCO nonstop | tree-absorption noise line, negative emissions sign |
| `test-case-gf-5` | STN→HND via IST, KIX | mixed airlines, blank lines, flat `+1`, layover-sourced KIX |
| `test-case-gf-rt` | gf-2 + gf-3 concatenated | two slices, differing prices (synthetic) |

The 32 existing tests must stay green in count and intent, but 10 of them pin
byte-exact output and will need regenerating for the source qualifier and the
decimal change: 6 reservation-UI snapshots, 2 email YAML fixtures, and 2
inline expected strings in `tests/test_render_email.py`. Each regenerated
fixture gets diffed against its predecessor to confirm only the header prefix
and the price precision moved.

## Out of scope

Emissions, contrail warming, legroom, Wi-Fi and amenity data are parsed past
but not stored or rendered. Multiple competing candidates in one paste are not
supported — one paste is one itinerary. Segment travel time is used as a
structural anchor but not retained.
