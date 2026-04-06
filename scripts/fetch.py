#!/usr/bin/env python3
"""Fetch planned disruptions from PRIM API and generate ICS files per metro line."""

import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, time as time_type, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import requests
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")


# Night service ends around 01:30–02:00, resumes around 05:00.
# Events ending before NIGHT_CUTOFF are "end of night", not start of next morning.
NIGHT_CUTOFF = time_type(5, 0)
# Night events (e.g. 22:00 → 04:30 next day) are stripped to NIGHT_STRIP_TO
# to make clear they belong to the previous evening.
NIGHT_STRIP_TO = time_type(2, 0)

ROOT = Path(__file__).parent.parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"

PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2"
BASE_URL = "https://travauxmetro.fr"
UMAMI = '<script defer src="https://cloud.umami.is/script.js" data-website-id="ef00b128-53c5-49eb-a0e9-e4da83748a67"></script>'
FAVICON = (
    '<link rel="icon" type="image/svg+xml" href="/favicon/favicon.svg">'
    '<link rel="icon" type="image/png" sizes="96x96" href="/favicon/favicon-96x96.png">'
    '<link rel="icon" type="image/x-icon" href="/favicon/favicon.ico">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/favicon/apple-touch-icon.png">'
    '<link rel="manifest" href="/favicon/site.webmanifest">'
)

# Line names match IDFM shortName (e.g. "3B" not "3bis")
# (bg_color, text_color)
METRO_LINE_COLORS = {
    "1":  ("#FFCD00", "#000000"),
    "2":  ("#003CA6", "#FFFFFF"),
    "3":  ("#837902", "#FFFFFF"),
    "3B": ("#6EC4E8", "#000000"),
    "4":  ("#CF009E", "#FFFFFF"),
    "5":  ("#FF7E2E", "#000000"),
    "6":  ("#6ECA97", "#000000"),
    "7":  ("#FA9ABA", "#000000"),
    "7B": ("#83C491", "#000000"),
    "8":  ("#E19BDF", "#000000"),
    "9":  ("#B6BD00", "#000000"),
    "10": ("#C9910D", "#000000"),
    "11": ("#704B1C", "#FFFFFF"),
    "12": ("#007852", "#FFFFFF"),
    "13": ("#98D4E2", "#000000"),
    "14": ("#62259D", "#FFFFFF"),
}


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


def fetch_data(token: str) -> dict:
    resp = requests.get(PRIM_URL, headers={"apikey": token}, timeout=30)
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def build_metro_index(lines: list) -> tuple[dict, dict, dict]:
    """
    Returns:
      metro_lines: {line_id -> line_dict}
      dis_to_line_ids: {disruption_id -> set of line_ids}
      dis_to_stops: {disruption_id -> {line_id -> [stop_name, ...]}}
    """
    metro_lines: dict = {}
    dis_to_line_ids: dict = defaultdict(set)
    dis_to_stops: dict = defaultdict(lambda: defaultdict(list))

    for line in lines:
        if line.get("mode") != "Metro":
            continue
        line_id = line["id"]
        metro_lines[line_id] = line
        for obj in line.get("impactedObjects", []):
            for dis_id in obj.get("disruptionIds", []):
                dis_to_line_ids[dis_id].add(line_id)
                if obj["type"] == "stop_point":
                    name = obj.get("name", "").strip()
                    stops = dis_to_stops[dis_id][line_id]
                    if name and name not in stops:
                        stops.append(name)

    return metro_lines, dis_to_line_ids, dis_to_stops


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r" +", " ", text).strip()


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=PARIS_TZ)


def normalize_period(dtstart: datetime, dtend: datetime) -> tuple[date | datetime, date | datetime, bool]:
    """
    Normalize a PRIM period to calendar-friendly bounds. Returns (ns, ne, is_allday).

    Full-day (is_allday=True): ns/ne are date objects; DTEND is ICS-exclusive.
      - Triggered when end < NIGHT_CUTOFF AND (start < NIGHT_CUTOFF OR span > 1 day).
      - Disrupted days: ns to ne-1 day inclusive (ne is exclusive in ICS).
      - A period ending at 04:30 on day D+N means day D+N is NOT disrupted.

    Night strip (is_allday=False): keep as datetime, strip end to NIGHT_STRIP_TO.
      - Triggered when start >= NIGHT_CUTOFF AND span == 1 day AND end < NIGHT_CUTOFF.
      - e.g. 22:00 Mon → 04:30 Tue becomes 22:00 Mon → 02:00 Tue.

    Otherwise: returned as-is.
    """
    start_t = dtstart.time()
    end_t = dtend.time()
    span_days = (dtend.date() - dtstart.date()).days
    end_before_cutoff = end_t < NIGHT_CUTOFF

    if end_before_cutoff and (start_t < NIGHT_CUTOFF or span_days > 1):
        return dtstart.date(), dtend.date(), True
    if end_before_cutoff and span_days == 1 and start_t >= NIGHT_CUTOFF:
        stripped = dtend.replace(hour=NIGHT_STRIP_TO.hour, minute=0, second=0, microsecond=0)
        return dtstart, stripped, False
    return dtstart, dtend, False


def period_key(dtstart: datetime, dtend: datetime) -> tuple:
    """Return the normalized (ns, ne) key for use in availability sets."""
    ns, ne, _ = normalize_period(dtstart, dtend)
    return (ns, ne)


def content_hash(disruptions: list, metro_dis_ids: set) -> str:
    relevant = sorted(
        [d for d in disruptions if d["id"] in metro_dis_ids],
        key=lambda d: d["id"],
    )
    key = [
        {
            "id": d["id"],
            "periods": d.get("applicationPeriods"),
            "severity": d.get("severity"),
            "cause": d.get("cause"),
            "title": d.get("title"),
        }
        for d in relevant
    ]
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


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
    return cal


def make_events(disruption: dict, line_name: str, stops: list[str]) -> list[Event]:
    title = disruption.get("title", "").strip()
    message = strip_html(disruption.get("message", ""))
    short = disruption.get("shortMessage", "").strip()
    cause = disruption.get("cause", "")

    summary = f"M{line_name} — {title or short or 'Perturbation'}"

    desc_parts = [f"Ligne {line_name}"]
    if stops:
        desc_parts.append(f"Station{'s' if len(stops) > 1 else ''} : {', '.join(stops)}")
    if short:
        desc_parts.append(short)
    if message and message != title:
        desc_parts.append(message)
    if cause:
        desc_parts.append(f"Cause : {cause}")
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
        e.add("dtstamp", datetime.now(timezone.utc))
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


def classify_disruptions(dis_ids: set, dis_by_id: dict) -> tuple[set, set]:
    """Split disruption IDs into (normal, umbrella).

    An umbrella is a single-period disruption whose span contains periods from
    other disruptions on the same line. Genuine continuous closures (e.g. a
    week-long shutdown) have no other disruptions nested inside them and are
    classified as normal.
    """
    # Collect all specific periods: multi-period disruptions, or single-period
    # ones shorter than 48 h — these are the concrete individual events.
    specific_periods: list[tuple] = []
    for dis_id in dis_ids:
        periods = dis_by_id[dis_id].get("applicationPeriods", [])
        if len(periods) > 1:
            for p in periods:
                specific_periods.append((parse_dt(p["begin"]), parse_dt(p["end"])))
        elif len(periods) == 1:
            dt_s, dt_e = parse_dt(periods[0]["begin"]), parse_dt(periods[0]["end"])
            if (dt_e - dt_s).total_seconds() < 48 * 3600:
                specific_periods.append((dt_s, dt_e))

    normal: set = set()
    umbrella: set = set()
    for dis_id in dis_ids:
        periods = dis_by_id[dis_id].get("applicationPeriods", [])
        if len(periods) == 1:
            dt_s, dt_e = parse_dt(periods[0]["begin"]), parse_dt(periods[0]["end"])
            if (dt_e - dt_s).total_seconds() >= 48 * 3600:
                if any(dt_s <= sp_s and sp_e <= dt_e for sp_s, sp_e in specific_periods):
                    umbrella.add(dis_id)
                    continue
        normal.add(dis_id)

    return normal, umbrella


def line_sort_key(name: str) -> tuple:
    mapping = {"3B": 3.5, "7B": 7.5}
    if name in mapping:
        return (mapping[name],)
    try:
        return (float(name),)
    except ValueError:
        return (999,)


def generate_summary(by_line: dict, dis_to_stops: dict, dis_by_id: dict, metro_lines: dict, fetched_at: str, diff: dict | None = None, event_counts: dict | None = None) -> str:
    date_str = f"{fetched_at[8:10]}-{fetched_at[5:7]}-{fetched_at[:4]}"
    name_to_id = {l["shortName"]: lid for lid, l in metro_lines.items()}

    def badge(line_name: str) -> str:
        bg, _ = METRO_LINE_COLORS.get(line_name, ("#888888", "#FFFFFF"))
        return f"![M{line_name}](https://img.shields.io/badge/-M{line_name}-{bg[1:]}?style=flat)"

    lines = [f"## Travaux métro — {date_str}", ""]

    if diff:
        lines.append("### Changements")
        lines.append("")
        for line_name in sorted(diff.keys(), key=line_sort_key):
            d = diff[line_name]
            parts = []
            if d["added"]:
                parts.append(f"+{d['added']}")
            if d["removed"]:
                parts.append(f"-{d['removed']}")
            lines.append(f"{badge(line_name)} {' '.join(parts)}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines += [
        f"**Lignes concernées :** {len(by_line)}",
        "",
        "| Ligne | Perturbations |",
        "|-------|--------------|",
    ]
    for line_name, dis_ids in sorted(by_line.items(), key=lambda x: line_sort_key(x[0])):
        count = event_counts.get(line_name, len(dis_ids)) if event_counts else len(dis_ids)
        lines.append(f"| {badge(line_name)} | {count} |")

    lines += ["", "---", ""]
    for line_name, dis_ids in sorted(by_line.items(), key=lambda x: line_sort_key(x[0])):
        lines.append(f"#### {badge(line_name)}")
        line_id = name_to_id.get(line_name)

        # Build the same deduplicated period set used for ICS generation
        normal_ids, _ = classify_disruptions(dis_ids, dis_by_id)
        all_events = []
        for dis_id in normal_ids:
            all_events.extend(make_events(dis_by_id[dis_id], line_name, dis_to_stops[dis_id].get(line_id, [])))
        available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

        for dis_id in sorted(normal_ids):
            d = dis_by_id[dis_id]
            title = d.get("title", "Perturbation").strip()
            short = d.get("shortMessage", "").strip()
            message = strip_html(d.get("message", ""))
            stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []

            # Only show periods that survived deduplication
            surviving = []
            for p in d.get("applicationPeriods", []):
                key = period_key(parse_dt(p["begin"]), parse_dt(p["end"]))
                if key in available:
                    surviving.append(p)
                    available.discard(key)

            if not surviving:
                continue

            period_str = (
                f"{fmt_date(surviving[0]['begin'])} → {fmt_date(surviving[-1]['end'])}"
                if surviving else ""
            )
            lines.append(f"- **{title}**" + (f" — {period_str}" if period_str else ""))
            if stops:
                lines.append(f"  - 🚉 {', '.join(stops)}")
            if short and short != title:
                lines.append(f"  - {short}")
            if message and message not in (title, short):
                truncated = message[:300] + ("…" if len(message) > 300 else "")
                lines.append(f"  - {truncated}")
        lines.append("")

    lines += [
        "---",
        "**Source :** [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)",
        "",
        "```bash",
        "curl -s -H \"apikey: $PRIM_TOKEN\" \\",
        "  \"https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2\" \\",
        "  | jq '[.disruptions[] | select(.cause == \"TRAVAUX\")]'",
        "```",
    ]
    return "\n".join(lines)


_WEBCAL_ICON = '<img src="/icons/apple.svg" width="16" height="16" alt="" style="margin-right:.35em;flex-shrink:0">'
_GCAL_ICON = '<img src="/icons/googlecalendar.svg" width="15" height="15" alt="" style="margin-right:.35em;flex-shrink:0">'
_OUTLOOK_ICON = '<img src="/icons/outlook.svg" width="16" height="16" alt="" style="margin-right:.35em;flex-shrink:0">'
_O365_ICON = '<img src="/icons/office365.svg" width="15" height="15" alt="" style="margin-right:.35em;flex-shrink:0">'
_COPY_ICON = '<img src="/icons/copy.svg" width="14" height="14" alt="" style="margin-right:.35em;flex-shrink:0">'


def _sub_buttons(full_url: str, line: str) -> str:
    webcal_url = full_url.replace("https://", "webcal://")
    encoded_https = full_url.replace("://", "%3A%2F%2F").replace("/", "%2F")
    gcal_url = f"https://calendar.google.com/calendar/render?cid={webcal_url.replace('://', '%3A%2F%2F').replace('/', '%2F')}"
    outlook_url = f"https://outlook.live.com/calendar/0/addfromweb?url={encoded_https}"
    o365_url = f"https://outlook.office.com/calendar/addfromweb?url={encoded_https}"
    return (
        f'<a class="sub-btn google" href="{gcal_url}" target="_blank" rel="noopener" data-umami-event="subscribe-google" data-umami-event-line="{line}">{_GCAL_ICON}Google Calendar</a>'
        f'<a class="sub-btn webcal" href="{webcal_url}" data-umami-event="subscribe-webcal" data-umami-event-line="{line}">{_WEBCAL_ICON}iCal / webcal</a>'
        f'<a class="sub-btn outlook" href="{outlook_url}" target="_blank" rel="noopener" data-umami-event="subscribe-outlook" data-umami-event-line="{line}">{_OUTLOOK_ICON}Outlook</a>'
        f'<a class="sub-btn o365" href="{o365_url}" target="_blank" rel="noopener" data-umami-event="subscribe-o365" data-umami-event-line="{line}">{_O365_ICON}Office 365</a>'
        f'<button class="sub-btn copy" onclick="copyUrl(\'{full_url}\',this)" data-umami-event="copy-url" data-umami-event-line="{line}">{_COPY_ICON}Copier le lien</button>'
    )


def fmt_dt(s: str) -> str:
    """YYYYMMDDTHHmmss → '25-04-2026 06:00'"""
    dt = datetime.strptime(s, "%Y%m%dT%H%M%S")
    return f"{dt.day:02d}-{dt.month:02d}-{dt.year} {dt.hour:02d}:{dt.minute:02d}"


def fmt_date(s: str) -> str:
    """YYYYMMDD... → 'DD-MM-YYYY'"""
    return f"{s[6:8]}-{s[4:6]}-{s[:4]}"


def fmt_period_display(p: dict) -> str:
    """Format a PRIM period dict using normalized bounds."""
    def fdate(d: date) -> str:
        return f"{d.day:02d}-{d.month:02d}-{d.year}"

    def fdt(dt: datetime) -> str:
        return f"{dt.day:02d}-{dt.month:02d}-{dt.year} {dt.hour:02d}:{dt.minute:02d}"

    ns, ne, is_allday = normalize_period(parse_dt(p["begin"]), parse_dt(p["end"]))
    if is_allday:
        last = ne - timedelta(days=1)
        return fdate(ns) if ns == last else f"{fdate(ns)} → {fdate(last)}"
    return f"{fdt(ns)} → {fdt(ne)}"


def _line_disruption_html(
    line_name: str,
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
) -> str:
    """Return the disruption details block (accordion or quiet note) for one line."""
    line_id = next((lid for lid, l in metro_lines.items() if l["shortName"] == line_name), None)
    all_ids = by_line.get(line_name, set())
    normal_ids, umbrella_ids = classify_disruptions(all_ids, dis_by_id)

    all_events = []
    for dis_id in normal_ids:
        stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []
        all_events.extend(make_events(dis_by_id[dis_id], line_name, stops))
    available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

    notes_html = ""
    for dis_id in sorted(umbrella_ids):
        d = dis_by_id[dis_id]
        msg = strip_html(d.get("message", "") or d.get("shortMessage", ""))
        if msg:
            notes_html += f'<p class="note">ℹ️ {html.escape(msg)}</p>'

    cards = ""
    for dis_id in sorted(normal_ids):
        d = dis_by_id[dis_id]
        title = d.get("title", "").strip()
        short = d.get("shortMessage", "").strip()
        message = strip_html(d.get("message", ""))
        stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []

        surviving = []
        for p in d.get("applicationPeriods", []):
            key = period_key(parse_dt(p["begin"]), parse_dt(p["end"]))
            if key in available:
                surviving.append(p)
                available.discard(key)

        if not surviving:
            continue

        periods_html = "".join(
            f'<div class="period">📅 {fmt_period_display(p)}</div>'
            for p in surviving
        )
        stops_html = f'<div class="stops">🚉 {", ".join(stops)}</div>' if stops else ""
        message_html = f'<div class="message">{message}</div>' if message else ""

        cards += f"""
          <div class="dis-card">
            <div class="card-title">{title or short or "Perturbation"}</div>
            {periods_html}{stops_html}{message_html}
          </div>"""

    card_count = cards.count('<div class="dis-card">')
    if card_count == 0:
        return '<p class="quiet">Aucune perturbation en cours, mais cela pourrait arriver dans le futur. Abonnez-vous pour ne pas les manquer.</p>'

    label = f"{card_count} perturbation{'s' if card_count > 1 else ''} en cours"
    return f"""<details>
      <summary>{label}</summary>
      {notes_html}<div class="cards">{cards}
      </div>
    </details>"""


def generate_index(
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
    fetched_at: str,
) -> str:
    all_url = f"{BASE_URL}/all.ics"
    date_str = fetched_at[:10]
    fetched_dt = datetime.fromisoformat(fetched_at).astimezone(PARIS_TZ)
    time_str = fetched_dt.strftime("%H:%M")

    disrupted_rows = ""
    calm_rows = ""
    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, fg = METRO_LINE_COLORS[line_name]
        full_url = f"{BASE_URL}/ligne-{line_name}.ics"
        badge = f'<span class="badge" style="background:{bg};color:{fg}">M{line_name}</span>'
        if by_line.get(line_name):
            dis_html = _line_disruption_html(line_name, by_line, dis_by_id, dis_to_stops, metro_lines)
            disrupted_rows += f"""
    <div class="line-row">
      {badge}
      <hr class="line-sep">
      <div class="line-actions">{_sub_buttons(full_url, line_name)}</div>
      {dis_html}
    </div>"""
        else:
            calm_rows += f"""
    <div class="line-row">
      {badge}
      <hr class="line-sep">
      <div class="line-actions">{_sub_buttons(full_url, line_name)}</div>
    </div>"""

    all_badges = " ".join(
        f'<span class="badge" style="background:{bg};color:{fg}">M{n}</span>'
        for n, (bg, fg) in sorted(METRO_LINE_COLORS.items(), key=lambda x: line_sort_key(x[0]))
    )

    disrupted_section = f"""
  <section>
    <h2 class="section-title">Lignes perturbées</h2>
    {disrupted_rows}
  </section>""" if disrupted_rows else '<p class="quiet" style="margin-bottom:1.5rem">Aucune perturbation en cours sur le réseau.</p>'

    calm_section = f"""
  <section>
    <h2 class="section-title">Autres lignes</h2>
    <p class="section-note">Aucune perturbation en cours sur ces lignes. Abonnez-vous pour être notifié automatiquement si cela change.</p>
    {calm_rows}
  </section>""" if calm_rows else ""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Travaux Métro à Paris</title>
  {FAVICON}
  {UMAMI}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; line-height: 1.5; background: #f7f7f7; }}
    h1 {{ margin-bottom: .25rem; font-size: 2.8rem; }}
    .subtitle {{ color: #555; margin-top: 0; margin-bottom: 1.5rem; }}
    .meta {{ color: #888; font-size: .85em; }}
    .intro {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: .9rem 1.1rem; margin-bottom: 1.5rem; font-size: .95em; }}
    a {{ color: #555; }}
    footer {{ margin-top: 3rem; color: #888; font-size: .85em; border-top: 1px solid #e8e8e8; padding-top: 1rem; line-height: 1.8; }}
    .badge {{ display: inline-block; padding: .2em .6em; border-radius: 5px; font-weight: 800; font-size: 1.75rem; min-width: 2.5em; text-align: center; flex-shrink: 0; }}
    .line-actions {{ display: flex; align-items: stretch; gap: .4rem; flex-wrap: wrap; }}
    @media (max-width: 480px) {{ .line-actions {{ flex-direction: column; align-items: flex-start; }} }}
    .sub-btn.copy {{ background: #888; color: #fff; }}
    .sub-btn.copy:hover {{ background: #666; }}
    .sub-btn.copy.copied {{ background: #2e7d32; justify-content: center; }}
    .sub-btn {{ display: inline-flex; align-items: center; cursor: pointer; border: none; border-radius: 5px; padding: .35em .85em; font-size: .82em; margin: 0; text-decoration: none; white-space: nowrap; font-family: inherit; line-height: 1; }}
    .sub-btn.webcal {{ background: #444; color: #fff; }}
    .sub-btn.webcal:hover {{ background: #222; }}
    .sub-btn.outlook {{ background: #0078d4; color: #fff; }}
    .sub-btn.outlook:hover {{ background: #005fa3; }}
    .sub-btn.o365 {{ background: #D83B01; color: #fff; }}
    .sub-btn.o365:hover {{ background: #b03000; }}
    .sub-btn.google {{ background: #4285F4; color: #fff; }}
    .sub-btn.google:hover {{ background: #2b6fd4; }}
    .section-title {{ font-size: 1.6rem; font-weight: 700; color: #333; text-transform: uppercase; letter-spacing: .06em; margin: 1.5rem 0 .75rem; }}
    .line-row {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: .85rem 1rem; margin-bottom: .75rem; }}
    .line-sep {{ border: none; border-top: 1px solid #f0f0f0; margin: .6rem 0 .5rem; }}
    .section-note {{ font-size: .85em; color: #aaa; margin: -.25rem 0 .75rem; }}
    .quiet {{ color: #aaa; font-size: .85em; margin: .5rem 0 0; }}
    details {{ margin-top: .6rem; }}
    details summary {{ cursor: pointer; font-size: .88em; color: #c0392b; font-weight: 600; list-style: none; display: flex; align-items: center; gap: .4rem; user-select: none; }}
    details summary::before {{ content: "▶"; font-size: .7em; transition: transform .15s; }}
    details[open] summary::before {{ transform: rotate(90deg); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: .75rem; margin-top: .75rem; }}
    .dis-card {{ background: #fafafa; border: 1px solid #e8e8e8; border-radius: 7px; padding: .8rem; }}
    .card-title {{ font-weight: 600; font-size: .9em; margin-bottom: .4rem; }}
    .period {{ font-size: .8em; color: #555; margin: .15rem 0; }}
    .stops {{ font-size: .8em; color: #333; margin-top: .35rem; }}
    .message {{ font-size: .78em; color: #666; margin-top: .45rem; border-top: 1px solid #eee; padding-top: .35rem; white-space: pre-wrap; }}
    .note {{ font-size: .82em; color: #666; font-style: italic; margin: .5rem 0 .5rem; }}
    .all-badges {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 0; }}
    .all-badges .badge {{ font-size: .75rem; padding: .15em .5em; }}
    section {{ margin-bottom: 2.5rem; }}
    @keyframes redglow {{ 0%, 100% {{ color: #8b1a1a; }} 50% {{ color: #e53935; }} }}
    .line-row details summary {{ font-size: 1rem; animation: redglow 3s ease-in-out infinite; }}
    @keyframes fadein {{ from {{ opacity: 0; transform: translateY(-6px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    details[open] .cards, details[open] .note {{ animation: fadein .5s ease; }}
  </style>
</head>
<body>
  <h1>Travaux Métro</h1>
  <p class="subtitle">Perturbations et travaux planifiés par Île-de-France Mobilités.</br>Abonnez-vous au calendrier d'interruptions de votre ligne de métro parisien.</p>

  <div class="intro">
    Cliquez sur <strong>le fournisseur de calendrier de votre choix</strong> pour vous abonner en un clic.</br>
    Le calendrier se met à jour <strong>automatiquement</strong>.
    <details style="margin-top:.6rem">
      <summary style="color:#888;font-weight:500">Comment ça marche ?</summary>
      <p style="margin:.5rem 0 0;font-size:.88em;color:#555">
        Un abonnement <a href="https://fr.wikipedia.org/wiki/ICalendar" target="_blank" rel="noopener" style="color:#555">iCalendar (aussi abrégé iCal)</a> est un calendrier en lecture seule hébergé sur Internet que votre application de calendrier récupère à intervale régulier.
        Les événements apparaissent directement dans votre agenda, sans compte supplémentaire à créer.
        Dès que de nouvelles perturbations sont prévues et publiées par Île-de-France Mobilités, elles se synchronisent automatiquement.
      </p>
    </details>
  </div>

  {disrupted_section}
  {calm_section}

  <section>
    <h2 class="section-title">Toutes les lignes</h2>
    <p class="section-note">Un seul abonnement pour suivre toutes les perturbations du réseau en même temps.</p>
    <div class="line-row">
      <div class="all-badges">{all_badges}</div>
      <hr class="line-sep">
      <div class="line-actions">{_sub_buttons(all_url, "all")}</div>
    </div>
  </section>

  <footer>
    <div>Source : <a href="https://prim.iledefrance-mobilites.fr">Île-de-France Mobilités (PRIM)</a> —
    <a href="https://github.com/ggrelet/travauxmetro.fr"><img src="/icons/github.svg" width="14" height="14" alt="GitHub" style="vertical-align:middle;margin-right:.25em;margin-bottom:2px">code source</a></div>
    <div>Dernière mise à jour des données : {date_str} à {time_str}</div>
  </footer>
  <script>
  function copyUrl(url, btn) {{
    if (btn.disabled) return;
    btn.disabled = true;
    const orig = btn.innerHTML;
    btn.style.width = btn.offsetWidth + 'px';
    const done = () => {{
      btn.classList.add('copied');
      btn.innerHTML = '✓ Copié !';
      setTimeout(() => {{
        btn.innerHTML = orig;
        btn.classList.remove('copied');
        btn.style.width = '';
        btn.disabled = false;
      }}, 3000);
    }};
    const fallback = () => {{
      const ta = Object.assign(document.createElement('textarea'), {{
        value: url, style: 'position:fixed;opacity:0'
      }});
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      try {{ document.execCommand('copy'); }} catch(e) {{}}
      document.body.removeChild(ta);
      done();
    }};
    if (navigator.clipboard) {{
      navigator.clipboard.writeText(url).then(done).catch(fallback);
    }} else {{
      fallback();
    }}
  }}
  </script>
</body>
</html>"""


def main():
    token = os.environ.get("PRIM_TOKEN")
    if not token:
        sys.exit("ERROR: PRIM_TOKEN not set")

    print("Fetching disruptions from PRIM API...")
    data = fetch_data(token)

    metro_lines, dis_to_line_ids, dis_to_stops = build_metro_index(data.get("lines", []))
    disruptions = data.get("disruptions", [])
    dis_by_id = {d["id"]: d for d in disruptions}

    # Keep only planned construction works, not real-time incidents
    travaux_ids = {d["id"] for d in disruptions if d.get("cause") == "TRAVAUX"}
    metro_dis_ids = set(dis_to_line_ids.keys()) & travaux_ids
    metro_disruptions = [d for d in disruptions if d["id"] in metro_dis_ids]
    print(f"Total disruptions: {len(disruptions)} — Metro travaux: {len(metro_disruptions)} across {len(metro_lines)} line{'s' if len(metro_lines) > 1 else ''}")

    DATA.mkdir(exist_ok=True)
    hash_file = DATA / "disruptions_hash.txt"
    new_hash = content_hash(disruptions, metro_dis_ids)
    expected_ics = [PUBLIC / f"ligne-{name}.ics" for name in METRO_LINE_COLORS]
    missing_ics = any(not f.exists() for f in expected_ics)
    if hash_file.exists() and hash_file.read_text().strip() == new_hash and not missing_ics:
        print("No change — skipping.")
        return

    print("Content changed, generating files...")
    fetched_at = datetime.now(timezone.utc).isoformat()

    # Load previous by_line state for diff
    by_line_file = DATA / "by_line.json"
    old_by_line: dict[str, list] = json.loads(by_line_file.read_text()) if by_line_file.exists() else {}

    (DATA / "snapshot.json").write_text(
        json.dumps({"fetched_at": fetched_at, "disruptions": metro_disruptions}, ensure_ascii=False, indent=2)
    )
    hash_file.write_text(new_hash)

    # Group disruption IDs by line name — only TRAVAUX
    by_line: dict[str, set] = defaultdict(set)
    for dis_id in metro_dis_ids:
        for line_id in dis_to_line_ids[dis_id]:
            line_name = metro_lines[line_id]["shortName"]
            by_line[line_name].add(dis_id)

    # Compute diff vs previous state
    diff: dict[str, dict] = {}
    all_lines = set(by_line.keys()) | set(old_by_line.keys())
    for line in all_lines:
        new_ids = by_line.get(line, set())
        old_ids = set(old_by_line.get(line, []))
        added = len(new_ids - old_ids)
        removed = len(old_ids - new_ids)
        if added or removed:
            diff[line] = {"added": added, "removed": removed}

    # Persist current by_line for next run
    (by_line_file).write_text(
        json.dumps({name: sorted(ids) for name, ids in by_line.items()}, ensure_ascii=False, indent=2)
    )

    PUBLIC.mkdir(exist_ok=True)
    all_cal = make_calendar(
        "Paris Métro — Travaux",
        "#003CA6",
        "Perturbations et travaux planifiés sur toutes les lignes du métro parisien. "
        "Mis à jour quotidiennement depuis les données Île-de-France Mobilités. "
        "travauxmetro.fr",
    )
    line_stats = []

    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, _ = METRO_LINE_COLORS[line_name]
        desc = (
            f"Perturbations et travaux planifiés sur la ligne {line_name} du métro parisien. "
            "Mis à jour quotidiennement depuis les données Île-de-France Mobilités. "
            "travauxmetro.fr"
        )
        cal = make_calendar(f"Métro Ligne {line_name} — Travaux", bg, desc)
        event_count = 0

        line_id_match = next((lid for lid, l in metro_lines.items() if l["shortName"] == line_name), None)
        all_ids = by_line.get(line_name, set())
        normal_ids, _ = classify_disruptions(all_ids, dis_by_id)

        events = []
        for dis_id in normal_ids:
            disruption = dis_by_id[dis_id]
            stops = dis_to_stops[dis_id].get(line_id_match, []) if line_id_match else []
            events.extend(make_events(disruption, line_name, stops))

        for event in deduplicate_events(events):
            cal.add_component(event)
            all_cal.add_component(event)
            event_count += 1

        filename = f"ligne-{line_name}.ics"
        (PUBLIC / filename).write_bytes(cal.to_ical())
        if event_count:
            line_stats.append((line_name, filename, event_count))
        print(f"  M{line_name}: {event_count} event{'s' if event_count > 1 else ''} → {filename}")

    (PUBLIC / "all.ics").write_bytes(all_cal.to_ical())

    event_counts = {name: count for name, _, count in line_stats}
    (DATA / "summary.md").write_text(generate_summary(by_line, dis_to_stops, dis_by_id, metro_lines, fetched_at, diff, event_counts))
    (PUBLIC / "index.html").write_text(generate_index(by_line, dis_by_id, dis_to_stops, metro_lines, fetched_at))
    print(f"Done. Generated all.ics + {len(line_stats)} line file{'s' if len(line_stats) else ''}.")


if __name__ == "__main__":
    main()
