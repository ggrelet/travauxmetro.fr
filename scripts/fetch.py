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
BASE_URL = "https://ggrelet.github.io/travaux-metro"

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
        desc_parts.append(f"Stations : {', '.join(stops)}")
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


def line_sort_key(name: str) -> tuple:
    mapping = {"3B": 3.5, "7B": 7.5}
    if name in mapping:
        return (mapping[name],)
    try:
        return (float(name),)
    except ValueError:
        return (999,)


def generate_summary(by_line: dict, dis_to_stops: dict, dis_by_id: dict, fetched_at: str) -> str:
    date_str = f"{fetched_at[8:10]}-{fetched_at[5:7]}-{fetched_at[:4]}"
    lines = [
        f"## Travaux métro — {date_str}",
        "",
        f"**Lignes concernées :** {len(by_line)}",
        "",
        "| Ligne | Perturbations |",
        "|-------|--------------|",
    ]
    for line_name, dis_ids in sorted(by_line.items(), key=lambda x: line_sort_key(x[0])):
        lines.append(f"| M{line_name} | {len(dis_ids)} |")

    lines += ["", "---", ""]
    for line_name, dis_ids in sorted(by_line.items(), key=lambda x: line_sort_key(x[0])):
        lines.append(f"#### Ligne {line_name}")
        for dis_id in dis_ids:
            d = dis_by_id[dis_id]
            title = d.get("title", "Perturbation")
            periods = d.get("applicationPeriods", [])
            period_str = (
                f" ({fmt_date(periods[0]['begin'])} → {fmt_date(periods[-1]['end'])})"
                if periods else ""
            )
            lines.append(f"- {title}{period_str}")
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
        <td>{count} perturbation(s)</td>
        <td><code>{full_url}</code></td>
        <td><a href="{filename}">↓ .ics</a></td>
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
  <p><code>{all_url}</code> &nbsp;<a href="all.ics">↓ Télécharger all.ics</a></p>

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


MONTHS_FR = ["jan.", "fév.", "mars", "avr.", "mai", "juin",
             "juil.", "août", "sep.", "oct.", "nov.", "déc."]


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
        cards = ""
        for dis_id in sorted(by_line[line_name]):
            d = dis_by_id[dis_id]
            title = d.get("title", "").strip()
            short = d.get("shortMessage", "").strip()
            message = strip_html(d.get("message", ""))
            stops = dis_to_stops[dis_id].get(line_id, [])
            periods = d.get("applicationPeriods", [])

            periods_html = "".join(
                f'<div class="period">📅 {fmt_dt(p["begin"])} → {fmt_dt(p["end"])}</div>'
                for p in periods
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

        sections += f"""
    <section class="line-section">
      <h2>
        <span class="badge" style="background:{bg};color:{fg}">M{line_name}</span>
        Ligne {line_name}
        <span class="count">{len(by_line[line_name])} perturbation(s)</span>
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
  <title>Aperçu travaux métro — {date_str}</title>
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
  <h1>Aperçu travaux métro</h1>
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
    print(f"Total disruptions: {len(disruptions)} — Metro travaux: {len(metro_disruptions)} across {len(metro_lines)} line(s)")

    DATA.mkdir(exist_ok=True)
    hash_file = DATA / "disruptions_hash.txt"
    new_hash = content_hash(disruptions, metro_dis_ids)
    if hash_file.exists() and hash_file.read_text().strip() == new_hash:
        print("No change — skipping.")
        return

    print("Content changed, generating files...")
    fetched_at = datetime.now(timezone.utc).isoformat()

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

    PUBLIC.mkdir(exist_ok=True)
    all_cal = make_calendar("Paris Métro — Travaux", "#6B318C")
    line_stats = []

    for line_name in sorted(by_line.keys(), key=line_sort_key):
        bg, _ = METRO_LINE_COLORS.get(line_name, ("#888888", "#FFFFFF"))
        cal = make_calendar(f"Métro Ligne {line_name} — Travaux", bg)
        event_count = 0

        # Find the line_id for this line_name
        line_id = next(lid for lid, l in metro_lines.items() if l["shortName"] == line_name)

        for dis_id in by_line[line_name]:
            disruption = dis_by_id[dis_id]
            stops = dis_to_stops[dis_id].get(line_id, [])
            for event in make_events(disruption, line_name, stops):
                cal.add_component(event)
                all_cal.add_component(event)
                event_count += 1

        filename = f"line-{line_name}.ics"
        (PUBLIC / filename).write_bytes(cal.to_ical())
        line_stats.append((line_name, filename, event_count))
        print(f"  M{line_name}: {event_count} event(s) → {filename}")

    (PUBLIC / "all.ics").write_bytes(all_cal.to_ical())

    # Build by_line with full disruption dicts for summary
    by_line_dicts = {
        name: [dis_by_id[did] for did in dis_ids]
        for name, dis_ids in by_line.items()
    }
    (DATA / "summary.md").write_text(generate_summary(by_line, dis_to_stops, dis_by_id, fetched_at))
    (PUBLIC / "index.html").write_text(generate_index(line_stats))
    (PUBLIC / "preview.html").write_text(generate_preview(by_line, dis_by_id, dis_to_stops, metro_lines, fetched_at))
    print(f"Done. Generated all.ics + {len(line_stats)} line file(s).")


if __name__ == "__main__":
    main()
