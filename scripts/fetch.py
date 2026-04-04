#!/usr/bin/env python3
"""Fetch planned disruptions from PRIM API and generate ICS files per metro line."""

import hashlib
import json
import os
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

PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk"
BASE_URL = "https://ggrelet.github.io/travaux-metro"

# Official RATP line colors
METRO_LINE_COLORS = {
    "1":    ("#FFCD00", "#000000"),
    "2":    ("#003CA6", "#FFFFFF"),
    "3":    ("#837902", "#FFFFFF"),
    "3bis": ("#6EC4E8", "#000000"),
    "4":    ("#CF009E", "#FFFFFF"),
    "5":    ("#FF7E2E", "#000000"),
    "6":    ("#6ECA97", "#000000"),
    "7":    ("#FA9ABA", "#000000"),
    "7bis": ("#83C491", "#000000"),
    "8":    ("#E19BDF", "#000000"),
    "9":    ("#B6BD00", "#000000"),
    "10":   ("#C9910D", "#000000"),
    "11":   ("#704B1C", "#FFFFFF"),
    "12":   ("#007852", "#FFFFFF"),
    "13":   ("#98D4E2", "#000000"),
    "14":   ("#62259D", "#FFFFFF"),
}

LINE_SORT_KEY = {"3bis": "3.5", "7bis": "7.5"}


def fetch_all_disruptions(token: str) -> list:
    """Paginate through the disruptions_bulk endpoint."""
    headers = {"apikey": token}
    now = datetime.now(timezone.utc)
    params = {
        "since": now.strftime("%Y%m%dT%H%M%S"),
        "count": 100,
    }
    disruptions = []
    page = 0
    while True:
        params["start_page"] = page
        resp = requests.get(PRIM_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("disruptions", [])
        disruptions.extend(batch)
        total = data.get("pagination", {}).get("total_result", len(disruptions))
        if len(disruptions) >= total or not batch:
            break
        page += 1
        print(f"  page {page}: {len(disruptions)}/{total}")
    return disruptions


def is_metro_line(pt_object: dict) -> bool:
    if pt_object.get("embedded_type") != "line":
        return False
    modes = pt_object.get("line", {}).get("physical_modes", [])
    return any("Metro" in m.get("id", "") for m in modes)


def get_metro_line_name(pt_object: dict) -> str | None:
    if is_metro_line(pt_object):
        return pt_object.get("name") or pt_object.get("line", {}).get("name")
    return None


def get_stops_for_line(disruption: dict, line_name: str) -> list[str]:
    stops = []
    for obj in disruption.get("impacted_objects", []):
        if get_metro_line_name(obj.get("pt_object", {})) == line_name:
            for stop in obj.get("impacted_stops", []):
                name = (
                    stop.get("stop_point", {}).get("name")
                    or stop.get("stop_point", {}).get("stop_area", {}).get("name")
                )
                if name and name not in stops:
                    stops.append(name)
    return stops


def get_message(disruption: dict) -> str:
    messages = disruption.get("messages", [])
    for msg in messages:
        if msg.get("channel", {}).get("name") == "titre":
            return msg.get("text", "").strip()
    return messages[0].get("text", "").strip() if messages else ""


def parse_navitia_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def content_hash(disruptions: list) -> str:
    """Hash of substantive disruption data, ignoring fetch timestamps."""
    key = [
        {
            "id": d.get("id"),
            "effect": d.get("severity", {}).get("effect"),
            "cause": d.get("cause"),
            "periods": d.get("application_periods"),
            "objects": sorted(
                obj.get("pt_object", {}).get("id", "")
                for obj in d.get("impacted_objects", [])
            ),
        }
        for d in sorted(disruptions, key=lambda x: x.get("id", ""))
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


def disruption_to_events(disruption: dict, line_name: str) -> list[Event]:
    stops = get_stops_for_line(disruption, line_name)
    message = get_message(disruption)
    cause = disruption.get("cause", "")
    severity_name = disruption.get("severity", {}).get("name", "Perturbation")

    stops_str = ", ".join(stops) if stops else "toute la ligne"
    summary = f"M{line_name} — {message[:60]}" if message else f"M{line_name} — {stops_str}"

    description_parts = [f"Ligne {line_name}"]
    if stops:
        description_parts.append(f"Stations affectées : {', '.join(stops)}")
    if severity_name:
        description_parts.append(f"Type : {severity_name}")
    if cause:
        description_parts.append(f"Cause : {cause}")
    if message:
        description_parts.append(f"\n{message}")
    description = "\n".join(description_parts)

    events = []
    for period in disruption.get("application_periods", []):
        try:
            dtstart = parse_navitia_dt(period["begin"])
            dtend = parse_navitia_dt(period["end"])
        except (KeyError, ValueError):
            continue

        event = Event()
        event.add("uid", f"{disruption.get('id', uuid4())}_{period['begin']}@travaux-metro")
        event.add("summary", summary)
        event.add("description", description)
        event.add("dtstart", dtstart)
        event.add("dtend", dtend)
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("categories", [f"Ligne {line_name}", "Travaux Métro"])
        events.append(event)
    return events


def sort_line_key(name: str) -> tuple:
    numeric = LINE_SORT_KEY.get(name, name)
    try:
        return (0, float(numeric), "")
    except ValueError:
        return (1, 0, name)


def generate_summary(by_line: dict, line_stats: list, fetched_at: str) -> str:
    lines = [
        f"## Travaux métro — {fetched_at[:10]}",
        "",
        f"**Lignes concernées :** {len(by_line)}",
        "",
        "| Ligne | Perturbations |",
        "|-------|--------------|",
    ]
    for line_name, _, count in line_stats:
        lines.append(f"| M{line_name} | {count} période(s) |")
    lines += ["", "### Détail", ""]
    for line_name, _, _ in line_stats:
        lines.append(f"#### Ligne {line_name}")
        for d in by_line[line_name]:
            msg = get_message(d)
            stops = get_stops_for_line(d, line_name)
            periods = d.get("application_periods", [])
            period_str = ""
            if periods:
                p = periods[0]
                period_str = f" ({p['begin'][:8]} → {p['end'][:8]})"
            stops_str = f" — {', '.join(stops[:4])}" if stops else ""
            lines.append(f"- {msg or 'Perturbation'}{stops_str}{period_str}")
        lines.append("")
    return "\n".join(lines)


def generate_index(line_stats: list) -> str:
    rows = ""
    for line_name, filename, count in line_stats:
        bg, fg = METRO_LINE_COLORS.get(line_name, ("#888", "#fff"))
        url = f"{BASE_URL}/{filename}"
        badge = f'<span class="badge" style="background:{bg};color:{fg}">M{line_name}</span>'
        rows += f"""
      <tr>
        <td>{badge}</td>
        <td>{count} période(s)</td>
        <td><code>{url}</code></td>
        <td><a href="{url}">↓ .ics</a></td>
      </tr>"""

    all_url = f"{BASE_URL}/all.ics"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Travaux Métro Paris — Calendrier ICS</title>
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
  </style>
</head>
<body>
  <h1>Travaux Métro Paris</h1>
  <p class="subtitle">Perturbations et travaux planifiés — abonnez-vous au calendrier de votre ligne.</p>

  <div class="card">
    <strong>Comment s'abonner :</strong> copiez une URL ci-dessous et ajoutez-la comme <em>calendrier par abonnement</em> dans votre application (Google Calendar, Apple Calendar, Outlook…). Le calendrier se met à jour automatiquement.
  </div>

  <h2>Toutes les lignes</h2>
  <p><code>{all_url}</code> &nbsp;<a href="{all_url}">↓ Télécharger all.ics</a></p>

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


def main():
    token = os.environ.get("PRIM_TOKEN")
    if not token:
        sys.exit("ERROR: PRIM_TOKEN environment variable not set")

    print("Fetching disruptions from PRIM API...")
    all_disruptions = fetch_all_disruptions(token)
    print(f"Total disruptions: {len(all_disruptions)}")

    metro_disruptions = [d for d in all_disruptions if any(
        is_metro_line(obj.get("pt_object", {}))
        for obj in d.get("impacted_objects", [])
    )]
    print(f"Metro disruptions: {len(metro_disruptions)}")

    # Skip writing files if content hasn't changed
    DATA.mkdir(exist_ok=True)
    hash_file = DATA / "disruptions_hash.txt"
    new_hash = content_hash(metro_disruptions)
    old_hash = hash_file.read_text().strip() if hash_file.exists() else ""
    if new_hash == old_hash:
        print("No change in disruption data — skipping file generation.")
        return

    print("Content changed, generating files...")
    fetched_at = datetime.now(timezone.utc).isoformat()

    # Save raw snapshot for PR review
    (DATA / "snapshot.json").write_text(
        json.dumps({"fetched_at": fetched_at, "disruptions": metro_disruptions}, ensure_ascii=False, indent=2)
    )
    hash_file.write_text(new_hash)

    # Group disruptions by metro line
    by_line: dict[str, list] = defaultdict(list)
    for d in metro_disruptions:
        for obj in d.get("impacted_objects", []):
            name = get_metro_line_name(obj.get("pt_object", {}))
            if name and d not in by_line[name]:
                by_line[name].append(d)

    PUBLIC.mkdir(exist_ok=True)
    all_cal = make_calendar("Paris Métro — Travaux", "#6B318C")
    line_stats = []

    for line_name in sorted(by_line.keys(), key=sort_line_key):
        bg, _ = METRO_LINE_COLORS.get(line_name, ("#888888", "#FFFFFF"))
        cal = make_calendar(f"Métro Ligne {line_name} — Travaux", bg)
        event_count = 0
        for disruption in by_line[line_name]:
            for event in disruption_to_events(disruption, line_name):
                cal.add_component(event)
                all_cal.add_component(event)
                event_count += 1
        filename = f"line-{line_name}.ics"
        (PUBLIC / filename).write_bytes(cal.to_ical())
        line_stats.append((line_name, filename, event_count))
        print(f"  M{line_name}: {event_count} event(s) → {filename}")

    (PUBLIC / "all.ics").write_bytes(all_cal.to_ical())
    print(f"Generated all.ics")

    # Write PR summary
    summary = generate_summary(by_line, line_stats, fetched_at)
    (DATA / "summary.md").write_text(summary)

    # Write index.html
    (PUBLIC / "index.html").write_text(generate_index(line_stats))
    print("Generated index.html")


if __name__ == "__main__":
    main()
