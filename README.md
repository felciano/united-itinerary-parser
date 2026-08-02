# United Itinerary Parser

Parse United Airlines itineraries into concise summaries.

## Usage

### Command Line

```bash
# From file
./summarize-united-itinerary.py itinerary.txt

# From stdin
cat itinerary.txt | ./summarize-united-itinerary.py

# From clipboard (macOS)
./summarize-united-itinerary.py
# Reads from clipboard, writes result back to clipboard
```

### PopClip Extension

1. Install the PopClip extension by double-clicking `United Itinerary.popclipext`
2. Select itinerary text on united.com
3. Click the airplane icon in the PopClip bar
4. Result is copied to clipboard

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
  - London Stansted (STN) to Tokyo Haneda (HND) (via Istanbul (IST), Osaka (KIX)):
    - STN > IST TK 1246: dep STN Wed Aug 26, 6:15 am, arr IST 12:10 pm (Economy, Boeing 737).
    - IST > KIX TK 86: dep IST Thu Aug 27, 2:25 am, arr KIX 7:05 pm (Economy, Boeing 787).
    - KIX > HND NH 98: dep KIX Thu Aug 27, 9:00 pm, arr HND 10:20 pm (Economy, Boeing 737).
```

Google Flights omits the year, so it is inferred from the printed weekday.

## Files

- `summarize-united-itinerary.py` - Main CLI script
- `summarize-united-itinerary.js` - Drafts app version
- `United Itinerary.popclipext/` - PopClip extension
- `test-cases/` - YAML test cases with input/expected output
