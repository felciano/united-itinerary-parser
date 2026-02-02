// Drafts script to convert a United itinerary to a terse Markdown summary
// Usage: Paste the United itinerary into a new draft and run the script

function parseUnitedItinerary(text) {
    const flightBlockPattern = /###\s+([A-Za-z ]+?) ([A-Z]{3}) to ([A-Za-z ]+?) ([A-Z]{3})\n+([A-Za-z]{3}), ([A-Za-z]+) (\d+)[^\n]*?\n.*?(\d{1,2}:\d{2} [AP]M) to (\d{1,2}:\d{2} [AP]M)(?:[^\n]*?\n)*?.*?(Nonstop|\d+ stop(?:over)?)/g;
    const flightNumPattern = /Flight Number: UA (\d+)/g;
    const durationPattern = /Duration: ([0-9h m]+)(?:\n|$)/g;
    const aircraftPattern = /Aircraft type: (.+)/g;
    const dateChangePattern = /involves a date change/gi;

    const flightNumMatches = [...text.matchAll(flightNumPattern)].map(m => m[1]);
    const durationMatches = [...text.matchAll(durationPattern)].map(m => m[1].trim().replace(/\s+/g, ''));
    const aircraftMatches = [...text.matchAll(aircraftPattern)].map(m => m[1]);

    let output = [];
    let match;
    let i = 0;

    while ((match = flightBlockPattern.exec(text)) !== null) {
        const [_, depCity, depAirport, arrCity, arrAirport, weekday, month, day, depTime, arrTime, stopType] = match;
        const flightNum = flightNumMatches[i];
        const duration = durationMatches[i] || null;
        const aircraft = aircraftMatches[i] || null;

        if (!flightNum) {
            output.push(`ERROR: Missing flight number for segment ${depAirport} > ${arrAirport}`);
            i++;
            continue;
        }

        const idxAfter = match.index + match[0].length;
        const dateChangeMatch = text.slice(idxAfter, idxAfter + 400).match(dateChangePattern);
        const arrDateNote = dateChangeMatch ? ` ${weekday === "Thu" ? "Fri" : "next day"}` : "";

        let extra = "";
        if (!duration && !aircraft) {
            extra = "dur/aircraft: ???";
        } else if (!duration) {
            extra = `aircraft: ${aircraft}`;
        } else if (!aircraft) {
            extra = `dur: ${duration}`;
        } else {
            extra = `${duration}, ${aircraft}`;
        }

        output.push(`- ${depAirport} > ${arrAirport} UA ${flightNum}: dep ${depAirport} ${weekday} ${month} ${day}, ${depTime.trim()}, arr ${arrAirport}${arrDateNote} ${arrTime.trim()} (${stopType.toLowerCase()}, ${extra}).`);
        i++;
    }

    // Match cost and upgrade info
    const costMatch = text.match(/Total due\s+\$([\d,]+\.\d{2})/);
    const milesMatch = text.match(/(\d{1,3}(,\d{3})*|\d+) miles/);
    const plusPointsMatch = text.match(/(\d{1,3}(,\d{3})*|\d+) PlusPoints/);

    let costLine = [];
    if (costMatch) costLine.push(`$${costMatch[1]}`);
    if (milesMatch) costLine.push(`${milesMatch[1].replace(/,/g, '')} miles`);
    if (plusPointsMatch) costLine.push(`${plusPointsMatch[1].replace(/,/g, '')} PlusPoints`);

    if (costLine.length > 0) {
        output.push("Cost: " + costLine.join(" + "));
    }

    return output.join("\n");
}

const text = draft.content;
const summary = parseUnitedItinerary(text);

if (summary) {
    const d = Draft.create();
    d.content = summary;
    d.update();
} else {
    alert('No valid United itinerary found.');
}
