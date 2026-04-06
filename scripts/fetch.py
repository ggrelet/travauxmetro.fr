#!/usr/bin/env python3
"""Fetch planned disruptions from PRIM API and generate ICS files per metro line."""

import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests
from icalendar import Calendar, Event

ROOT = Path(__file__).parent.parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"

PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2"
BASE_URL = "https://travauxmetro.fr"
UMAMI = '<script defer src="https://cloud.umami.is/script.js" data-website-id="ef00b128-53c5-49eb-a0e9-e4da83748a67"></script>'

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
    return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


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


def make_calendar(name: str, bg_color: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//ggrelet//travaux-metro//FR")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-timezone", "Europe/Paris")
    cal.add("x-apple-calendar-color", bg_color)
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
        e = Event()
        e.add("uid", f"{disruption['id']}_{period['begin']}@travaux-metro")
        e.add("summary", summary)
        e.add("description", description)
        e.add("dtstart", dtstart)
        e.add("dtend", dtend)
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
        all_events = []
        for dis_id in dis_ids:
            all_events.extend(make_events(dis_by_id[dis_id], line_name, dis_to_stops[dis_id].get(line_id, [])))
        available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

        for dis_id in sorted(dis_ids):
            d = dis_by_id[dis_id]
            title = d.get("title", "Perturbation").strip()
            short = d.get("shortMessage", "").strip()
            message = strip_html(d.get("message", ""))
            stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []

            # Only show periods that survived deduplication
            surviving = []
            for p in d.get("applicationPeriods", []):
                key = (parse_dt(p["begin"]), parse_dt(p["end"]))
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


def generate_index(line_stats: list[tuple]) -> str:
    rows = ""
    for line_name, filename, count in line_stats:
        bg, fg = METRO_LINE_COLORS.get(line_name, ("#888", "#fff"))
        full_url = f"{BASE_URL}/{filename}"
        badge = f'<span class="badge" style="background:{bg};color:{fg}">M{line_name}</span>'
        rows += f"""
      <tr>
        <td>{badge}</td>
        <td>{count} perturbation{'s' if count > 1 else ''}</td>
        <td><code>{full_url}</code></td>
        <td><button class="copy-btn" onclick="copyUrl('{full_url}', this)" data-umami-event="copy-url" data-umami-event-line="{line_name}">Copier l'URL</button></td>
      </tr>"""

    all_url = f"{BASE_URL}/all.ics"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Travaux Métro Paris — Calendrier ICS</title>
  {UMAMI}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; line-height: 1.5; }}
    h1 {{ margin-bottom: .25rem; }}
    .subtitle {{ color: #555; margin-top: 0; }}
    .badge {{ display: inline-block; padding: .15em .55em; border-radius: 4px; font-weight: 700; font-size: .9em; min-width: 2.5em; text-align: center; }}
    .card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; background: #fafafa; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #e0e0e0; padding: .45rem .9rem; text-align: left; }}
    th {{ background: #f4f4f4; font-weight: 600; }}
    code {{ background: #f0f0f0; padding: .1em .4em; border-radius: 3px; font-size: .82em; word-break: break-all; }}
    a {{ color: #6B318C; }}
    footer {{ margin-top: 3rem; color: #888; font-size: .85em; }}
    .copy-btn {{ cursor: pointer; background: #6B318C; color: #fff; border: none; border-radius: 4px; padding: .25em .7em; font-size: .85em; margin-left: .5rem; }}
    .copy-btn:hover {{ background: #552070; }}
    .copy-btn.copied {{ background: #2e7d32; }}
  </style>
</head>
<script>
function copyUrl(url, btn) {{
  navigator.clipboard.writeText(url).then(() => {{
    btn.textContent = 'Copié !';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = "Copier l'URL"; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
<body>
  <h1>Travaux Métro Paris</h1>
  <p class="subtitle">Perturbations et travaux planifiés — abonnez-vous au calendrier de votre ligne.</p>

  <div class="card">
    <strong>Comment s'abonner :</strong> copiez une URL ci-dessous et ajoutez-la comme <em>calendrier par abonnement</em> dans votre application (Google Calendar, Apple Calendar, Outlook…). Le calendrier se met à jour automatiquement.
  </div>

  <p><a href="overview.html">→ Aperçu visuel des perturbations</a></p>

  <h2>Toutes les lignes</h2>
  <p>
    <code>{all_url}</code>
    <button class="copy-btn" onclick="copyUrl('{all_url}', this)" data-umami-event="copy-url" data-umami-event-line="all">Copier l'URL</button>
  </p>

  <h2>Par ligne</h2>
  <table>
    <thead><tr><th>Ligne</th><th>Perturbations</th><th>URL d'abonnement</th><th></th></tr></thead>
    <tbody>{rows}
    </tbody>
  </table>

  <footer>
    Source : <a href="https://prim.iledefrance-mobilites.fr">Île-de-France Mobilités (PRIM)</a> —
    mis à jour quotidiennement via GitHub Actions —
    <a href="https://github.com/ggrelet/travaux-metro">code source</a>
  </footer>
</body>
</html>"""


def fmt_dt(s: str) -> str:
    """YYYYMMDDTHHmmss → '25-04-2026 06:00'"""
    dt = datetime.strptime(s, "%Y%m%dT%H%M%S")
    return f"{dt.day:02d}-{dt.month:02d}-{dt.year} {dt.hour:02d}:{dt.minute:02d}"


def fmt_date(s: str) -> str:
    """YYYYMMDD... → 'DD-MM-YYYY'"""
    return f"{s[6:8]}-{s[4:6]}-{s[:4]}"


def generate_preview(
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
    fetched_at: str,
) -> str:
    sections = ""
    for line_name in sorted(by_line.keys(), key=line_sort_key):
        bg, fg = METRO_LINE_COLORS.get(line_name, ("#888", "#fff"))
        line_id = next(lid for lid, l in metro_lines.items() if l["shortName"] == line_name)

        # Build the same deduplicated period set used for ICS generation
        all_events = []
        for dis_id in by_line[line_name]:
            all_events.extend(make_events(dis_by_id[dis_id], line_name, dis_to_stops[dis_id].get(line_id, [])))
        available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

        cards = ""
        for dis_id in sorted(by_line[line_name]):
            d = dis_by_id[dis_id]
            title = d.get("title", "").strip()
            short = d.get("shortMessage", "").strip()
            message = strip_html(d.get("message", ""))
            stops = dis_to_stops[dis_id].get(line_id, [])

            # Only show periods that survived deduplication; claim them so they
            # don't appear again in another card for the same line
            surviving = []
            for p in d.get("applicationPeriods", []):
                key = (parse_dt(p["begin"]), parse_dt(p["end"]))
                if key in available:
                    surviving.append(p)
                    available.discard(key)

            if not surviving:
                continue

            periods_html = "".join(
                f'<div class="period">📅 {fmt_dt(p["begin"])} → {fmt_dt(p["end"])}</div>'
                for p in surviving
            )
            stops_html = (
                f'<div class="stops">🚉 {", ".join(stops)}</div>' if stops else ""
            )
            message_html = f'<div class="message">{message}</div>' if message else ""

            cards += f"""
        <div class="card">
          <div class="card-title">{title or short or "Perturbation"}</div>
          {periods_html}
          {stops_html}
          {message_html}
        </div>"""

        card_count = cards.count('<div class="card">')
        sections += f"""
    <section class="line-section">
      <h2>
        <span class="badge" style="background:{bg};color:{fg}">M{line_name}</span>
        Ligne {line_name}
        <span class="count">{card_count} perturbation{'s' if card_count > 1 else '' }</span>
      </h2>
      <div class="cards">{cards}
      </div>
    </section>"""

    date_str = fetched_at[:10]
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vue d'ensemble travaux métro — {date_str}</title>
  {UMAMI}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; line-height: 1.5; background: #f7f7f7; }}
    h1 {{ margin-bottom: .1rem; }}
    .meta {{ color: #888; font-size: .9em; margin-bottom: 2rem; }}
    .line-section {{ margin-bottom: 2.5rem; }}
    .line-section h2 {{ display: flex; align-items: center; gap: .6rem; font-size: 1.1rem; margin-bottom: .75rem; }}
    .badge {{ display: inline-block; padding: .2em .6em; border-radius: 5px; font-weight: 800; font-size: 1em; min-width: 2.4em; text-align: center; }}
    .count {{ font-size: .8em; font-weight: 400; color: #888; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }}
    .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem; }}
    .card-title {{ font-weight: 600; margin-bottom: .5rem; }}
    .period {{ font-size: .82em; color: #555; margin: .2rem 0; }}
    .stops {{ font-size: .82em; color: #333; margin-top: .4rem; }}
    .message {{ font-size: .8em; color: #666; margin-top: .5rem; border-top: 1px solid #f0f0f0; padding-top: .4rem; white-space: pre-wrap; }}
    a {{ color: #6B318C; }}
  </style>
</head>
<body>
  <h1>Vue d'ensemble — Travaux métro</h1>
  <p class="meta">Données du {date_str} — <a href="index.html">← Retour</a></p>
  {sections}
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
    all_cal = make_calendar("Paris Métro — Travaux", "#6B318C")
    line_stats = []

    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, _ = METRO_LINE_COLORS[line_name]
        cal = make_calendar(f"Métro Ligne {line_name} — Travaux", bg)
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
    (PUBLIC / "index.html").write_text(generate_index(line_stats))
    (PUBLIC / "overview.html").write_text(generate_preview(by_line, dis_by_id, dis_to_stops, metro_lines, fetched_at))
    print(f"Done. Generated all.ics + {len(line_stats)} line file{'s' if len(line_stats) else ''}.")


if __name__ == "__main__":
    main()
