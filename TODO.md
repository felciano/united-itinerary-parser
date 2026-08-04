# TODO

Work queue. Nothing here blocks anything; these are findings deferred during
the Google Flights work (2026-08-02/03) with the reasoning that made them safe
to leave.

## Code

- [ ] **`parse_united_itinerary` is over the 30-line convention** — 59 lines and
  growing; it was 51 before this work. It is two things bolted together: a
  three-way dispatcher and the entire inlined reservation-UI path. Extracting
  `_render_reservation_ui(text)` leaves a ~12-line dispatcher and is a pure
  move, backed by six byte-exact snapshot fixtures. Cheapest item here.

- [ ] **`_GF_PRICE` matches things that are not prices** — `Aug 26` parses as
  `('Aug', '26')`, and a bare `+2` as `('+', '2')`. Harmless today only because
  the real date line carries a comma the pattern will not cross, and because
  the price is only searched within slice header lines. Tightening the symbol
  class to an explicit currency set would close it. Note the price *splitter*
  in `_normalize_gf_flattened` already uses the narrow class for exactly this
  reason — the two should agree.

- [ ] **`_summarize_reservation_ui` parses our own rendered output** — a
  deliberate trade (see AGENTS.md) rather than reworking two ~120-line
  string-building parsers. If those parsers are ever refactored to populate the
  dataclasses, delete this and use `_summarize_itinerary` like the other two
  formats.

- [ ] **The email header has mixed punctuation** — it ends without a period but
  keeps the internal one before `Accrual:`, since that is a separate sentence.
  Reads fine; flagged in case uniformity is wanted.

## Extension

- [ ] **Six orphaned extension rows in PopClip's database** — repeated installs
  stacked duplicates in `~/Library/Application Support/PopClip/Data/PopClip.sqlite`
  and PopClip executed the oldest, which cost most of a debugging session. The
  live one is the newest. Back up the database, quit PopClip, delete the
  orphans.

- [ ] **The extension name undersells it** — still "United Itinerary" with a
  "Parse United Itinerary" action, though it now handles Google Flights too.
  Renaming changes the identifier PopClip derives from the folder name, so do
  the duplicate cleanup above first or it will add yet another stacked copy.
  Adding an explicit `identifier` to `Config.json` would make future renames
  clean.

## Coverage

- [ ] **The flattened selected-trip case is tested against a synthesised
  flattening**, not a real PopClip capture, because no genuine capture of that
  view *including its preamble* was available. It works, but if it misbehaves,
  `run.sh` writes the real capture to `/tmp/popclip-united-text.txt` — pin that
  as a fixture and pair it with the clipboard one.

- [ ] **More Google Flights layouts almost certainly exist** — multi-city,
  mixed cabins, basic economy. Two layouts have been found so far and each
  broke parsing differently. An unrecognised layout yields no output rather
  than wrong output, so this degrades safely.
