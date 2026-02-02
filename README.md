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

## Output Format

```
- Itinerary: $2,207.63 + 40,000 miles
  - LHR > SFO UA 900: dep LHR Thu Feb 5, 10:05 am, arr SFO 1:20 pm (nonstop, 11h15m, Boeing 777-200ER).
  - SFO > LHR UA 901: dep SFO Wed Feb 11, 12:50 pm, arr LHR Thu 7:25 am (nonstop, 10h35m, Boeing 777-200).
```

## Files

- `summarize-united-itinerary.py` - Main CLI script
- `summarize-united-itinerary.js` - Drafts app version
- `United Itinerary.popclipext/` - PopClip extension
- `test-cases/` - YAML test cases with input/expected output
