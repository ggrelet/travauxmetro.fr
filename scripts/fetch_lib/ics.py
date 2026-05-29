"""ICS calendar & event generation, plus Google Calendar color snapping."""

import re
import sys
from datetime import datetime, timedelta

from icalendar import Calendar, Event, Timezone, TimezoneDaylight, TimezoneStandard

from .constants import BASE_URL, ROOT, _utc_now
from .prim import normalize_period, parse_dt, strip_html


# Google Calendar's fixed color palette (exact hex values from their API).
# Using these prevents snapping to a random/wrong color when subscribing via ICS.
_GOOGLE_PALETTE = {
    "Cocoa": "#ac725e", "Flamingo": "#d06b64", "Tomato": "#f83a22",
    "Tangerine": "#fa573c", "Pumpkin": "#ff7537", "Mango": "#ffad46",
    "Eucalyptus": "#42d692", "Basil": "#16a765", "Pistachio": "#7bd148",
    "Avocado": "#b3dc6c", "Citron": "#fbe983", "Banana": "#fad165",
    "Sage": "#92e1c0", "Peacock": "#9fe1e7", "Cobalt": "#9fc6e7",
    "Blueberry": "#4986e7", "Lavender": "#9a9cff", "Wisteria": "#b99aff",
    "Graphite": "#c2c2c2", "Birch": "#cabdbf", "Beetroot": "#cca6ac",
    "Cherry Blossom": "#f691b2", "Grape": "#cd74e6", "Amethyst": "#a47ae2",
}


def _load_gcal_colors() -> dict[str, str]:
    """Read gcal palette names from data/line-colors.md and resolve to hex."""
    palette_by_name = {k.lower(): v for k, v in _GOOGLE_PALETTE.items()}
    colors: dict[str, str] = {}
    for line in (ROOT / "data" / "line-colors.md").read_text().splitlines():
        m = re.match(r"\|\s*M(\S+)\s*\|[^|]+\|\s*([A-Za-z ]+\S)\s*\|", line)
        if m:
            name = m.group(2).strip()
            hex_color = palette_by_name.get(name.lower())
            if hex_color:
                colors[m.group(1)] = hex_color
            else:
                print(f"WARNING: unknown Google Calendar color '{name}' for M{m.group(1)}", file=sys.stderr)
    return colors


GCAL_COLORS: dict[str, str] = _load_gcal_colors()


def _nearest_google_color(hex_color: str) -> str:
    def to_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r1, g1, b1 = to_rgb(hex_color)
    return min(
        _GOOGLE_PALETTE.values(),
        key=lambda h: sum((a - b) ** 2 for a, b in zip(to_rgb(h), (r1, g1, b1))),
    )


def _paris_vtimezone() -> Timezone:
    """A minimal, RFC-5545 VTIMEZONE for Europe/Paris.

    Hand-built with RRULE-based EU DST rules rather than generated from the OS
    tz database, so the output is byte-stable across machines (tzdata versions
    differ between dev and CI). Two purposes:

    1. Events emit DTSTART;TZID=Europe/Paris, and the RFC requires any referenced
       TZID to be defined in the calendar — without this, the calendars are
       technically non-compliant.
    2. It guarantees every calendar has >=1 component, so feeds for lines with no
       current works are still valid (an empty VCALENDAR is not) and don't get
       rejected by strict parsers like Apple Calendar.
    """
    tz = Timezone()
    tz.add("tzid", "Europe/Paris")

    std = TimezoneStandard()
    std.add("dtstart", datetime(1996, 10, 27, 3, 0, 0))
    std.add("tzoffsetfrom", timedelta(hours=2))
    std.add("tzoffsetto", timedelta(hours=1))
    std.add("tzname", "CET")
    std.add("rrule", {"freq": "yearly", "bymonth": 10, "byday": "-1SU"})

    dst = TimezoneDaylight()
    dst.add("dtstart", datetime(1981, 3, 29, 2, 0, 0))
    dst.add("tzoffsetfrom", timedelta(hours=1))
    dst.add("tzoffsetto", timedelta(hours=2))
    dst.add("tzname", "CEST")
    dst.add("rrule", {"freq": "yearly", "bymonth": 3, "byday": "-1SU"})

    tz.add_component(std)
    tz.add_component(dst)
    return tz


def make_calendar(name: str, bg_color: str, description: str = "") -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//ggrelet//travaux-metro//FR")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-caldesc", description)
    cal.add("x-wr-timezone", "Europe/Paris")
    cal.add("x-apple-calendar-color", bg_color)
    cal.add("x-published-ttl", "PT12H")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add_component(_paris_vtimezone())
    return cal


def make_events(disruption: dict, line_name: str, stops: list[str], network: str = "Metro") -> list[Event]:
    title = disruption.get("title", "").strip()
    message = strip_html(disruption.get("message", ""))
    short = disruption.get("shortMessage", "").strip()
    cause = disruption.get("cause", "")

    summary = title or short or "Interruption"

    desc_parts = [f"Ligne {line_name}"]
    if stops:
        desc_parts.append(f"Station{'s' if len(stops) > 1 else ''} : {', '.join(stops)}")
    if short:
        desc_parts.append(short)
    if message and message != title:
        desc_parts.append(message)
    if cause:
        desc_parts.append(f"Cause : {cause}")
    desc_parts.append(f"{BASE_URL}/")
    description = "\n\n".join(desc_parts)

    events = []
    for period in disruption.get("applicationPeriods", []):
        try:
            dtstart = parse_dt(period["begin"])
            dtend = parse_dt(period["end"])
        except (KeyError, ValueError):
            continue
        ns, ne, _ = normalize_period(dtstart, dtend)
        e = Event()
        e.add("uid", f"{disruption['id']}_{period['begin']}@travaux-metro")
        e.add("summary", summary)
        e.add("description", description)
        e.add("dtstart", ns)
        e.add("dtend", ne)
        e.add("dtstamp", _utc_now())
        e.add("categories", [f"Ligne {line_name}", "Travaux Métro"])
        events.append(e)
    return events


def deduplicate_events(events: list[Event]) -> list[Event]:
    """PRIM sometimes emits both a batch record (all Sundays) and per-date records
    for the same disruption. Deduplicate by (dtstart, dtend), keeping the
    event with the longest description."""
    seen: dict[tuple, Event] = {}
    for event in events:
        key = (event.get("dtstart").dt, event.get("dtend").dt)
        existing = seen.get(key)
        if existing is None:
            seen[key] = event
        else:
            if len(str(event.get("description", ""))) > len(str(existing.get("description", ""))):
                seen[key] = event
    return list(seen.values())
