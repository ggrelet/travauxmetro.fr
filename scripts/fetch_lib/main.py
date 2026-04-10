"""Orchestration entry point: parses args, fetches, and writes all outputs."""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import constants
from .constants import METRO_LINE_COLORS, ROOT, _today, _utc_now
from .html import generate_index
from .ics import deduplicate_events, make_calendar, make_events
from .prim import (
    build_metro_index,
    classify_disruptions,
    content_hash,
    dis_fingerprint,
    fetch_data,
    line_sort_key,
)
from .summary import generate_summary


def main():
    parser = argparse.ArgumentParser(description="Fetch PRIM disruptions and generate site files.")
    parser.add_argument("--fixture", help="Load raw PRIM JSON from this path instead of calling the API.")
    parser.add_argument("--now", help="Override current time (ISO 8601, e.g. 2026-04-10T01:01:00+02:00).")
    parser.add_argument("--out-dir", help="Write outputs under this directory (creates public/ and data/ subdirs).")
    parser.add_argument("--save-raw", help="Fetch raw PRIM response, write it to this path, and exit.")
    parser.add_argument("--force", action="store_true", help="Skip the content-hash check and regenerate all files.")
    args = parser.parse_args()

    if args.now:
        constants.set_fake_now(datetime.fromisoformat(args.now))

    if args.out_dir:
        out_root = Path(args.out_dir)
        public = out_root / "public"
        data_dir = out_root / "data"
        public.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        public = ROOT / "public"
        data_dir = ROOT / "data"

    if args.fixture:
        print(f"Loading fixture → {args.fixture}")
        data = json.loads(Path(args.fixture).read_text())
    else:
        token = os.environ.get("PRIM_TOKEN")
        if not token:
            sys.exit("ERROR: PRIM_TOKEN not set")
        print("Fetching disruptions from PRIM API...")
        data = fetch_data(token)
        if args.save_raw:
            Path(args.save_raw).parent.mkdir(parents=True, exist_ok=True)
            Path(args.save_raw).write_text(json.dumps(data, ensure_ascii=False))
            print(f"Saved raw PRIM response → {args.save_raw}")
            return

    metro_lines, dis_to_line_ids, dis_to_stops = build_metro_index(data.get("lines", []))
    disruptions = data.get("disruptions", [])
    dis_by_id = {d["id"]: d for d in disruptions}

    # Keep only planned construction works, not real-time incidents
    travaux_ids = {d["id"] for d in disruptions if d.get("cause") == "TRAVAUX"}
    metro_dis_ids = set(dis_to_line_ids.keys()) & travaux_ids
    metro_disruptions = [d for d in disruptions if d["id"] in metro_dis_ids]
    print(f"Total disruptions: {len(disruptions)} — Metro travaux: {len(metro_disruptions)} across {len(metro_lines)} line{'s' if len(metro_lines) > 1 else ''}")

    data_dir.mkdir(exist_ok=True)
    hash_file = data_dir / "disruptions_hash.txt"
    new_hash = content_hash(disruptions, metro_dis_ids)
    expected_ics = [public / f"ligne-{name}.ics" for name in METRO_LINE_COLORS]
    missing_ics = any(not f.exists() for f in expected_ics)
    if not args.force and hash_file.exists() and hash_file.read_text().strip() == new_hash and not missing_ics:
        print("No change — skipping. (Pass --force to regenerate anyway.)")
        return

    print("Content changed, generating files...")
    fetched_at = _utc_now().isoformat()

    # Load previous by_line state for diff
    by_line_file = data_dir / "by_line.json"
    old_by_line: dict[str, list] = json.loads(by_line_file.read_text()) if by_line_file.exists() else {}

    # snapshot.json is --fixture-compatible: CI deploy regenerates the site from it
    # instead of committing generated HTML/ICS. Only metro lines are kept to keep
    # the file small; disruptions are already metro-travaux-filtered above.
    metro_line_entries = [line for line in data.get("lines", []) if line.get("id") in metro_lines]
    (data_dir / "snapshot.json").write_text(
        json.dumps(
            {"fetched_at": fetched_at, "lines": metro_line_entries, "disruptions": metro_disruptions},
            ensure_ascii=False,
            indent=2,
        )
    )
    hash_file.write_text(new_hash)

    # Group disruption IDs by line name — only TRAVAUX
    by_line: dict[str, set] = defaultdict(set)
    for dis_id in metro_dis_ids:
        for line_id in dis_to_line_ids[dis_id]:
            line_name = metro_lines[line_id]["shortName"]
            by_line[line_name].add(dis_id)

    # Compute diff vs previous state using content fingerprints (ignores UUID re-issues)
    def fp_set(line: str, source: dict) -> set:
        entries = source.get(line, [])
        # Migration: old format stored raw ID strings, new format stores fingerprints (lists)
        if entries and isinstance(entries[0], str):
            return set()
        return {frozenset(tuple(p) for p in fp) for fp in entries}

    # Sort IDs so by_line.json is byte-stable across runs (sets have random iteration order)
    new_fps_by_line = {
        line: [dis_fingerprint(dis_by_id[dis_id]) for dis_id in sorted(ids)]
        for line, ids in by_line.items()
    }
    diff: dict[str, dict] = {}
    all_lines = set(by_line.keys()) | set(old_by_line.keys())
    for line in all_lines:
        old_set = fp_set(line, old_by_line)
        new_set = {frozenset(tuple(p) for p in fp) for fp in new_fps_by_line.get(line, [])}
        added = len(new_set - old_set)
        removed = len(old_set - new_set)
        if added or removed:
            diff[line] = {"added": added, "removed": removed}

    # Persist fingerprints (not IDs) so UUID re-issues don't show as changes next run.
    # sort_keys keeps the file byte-stable across runs (dict key order is set-iteration-dependent).
    (by_line_file).write_text(
        json.dumps(new_fps_by_line, ensure_ascii=False, indent=2, sort_keys=True)
    )

    public.mkdir(exist_ok=True)
    all_cal = make_calendar(
        "Paris Métro — Travaux",
        "#003CA6",
        "Interruptions et travaux planifiés sur toutes les lignes du métro parisien. "
        "Mis à jour quotidiennement depuis les données Île-de-France Mobilités. "
        "travauxmetro.fr",
    )
    line_stats = []

    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, _ = METRO_LINE_COLORS[line_name]
        desc = (
            f"Interruptions et travaux planifiés sur la ligne {line_name} du métro parisien. "
            "Mis à jour quotidiennement depuis les données Île-de-France Mobilités. "
            "travauxmetro.fr"
        )
        cal = make_calendar(f"Métro Ligne {line_name} — Travaux", bg, desc)
        event_count = 0

        line_id_match = next((lid for lid, l in metro_lines.items() if l["shortName"] == line_name), None)
        all_ids = by_line.get(line_name, set())
        normal_ids, _ = classify_disruptions(all_ids, dis_by_id)

        # Sort IDs so ICS event order is byte-stable across runs
        events = []
        for dis_id in sorted(normal_ids):
            disruption = dis_by_id[dis_id]
            stops = dis_to_stops[dis_id].get(line_id_match, []) if line_id_match else []
            events.extend(make_events(disruption, line_name, stops))

        for event in deduplicate_events(events):
            cal.add_component(event)
            all_cal.add_component(event)
            event_count += 1

        filename = f"ligne-{line_name}.ics"
        (public / filename).write_bytes(cal.to_ical())
        if event_count:
            line_stats.append((line_name, filename, event_count))
        print(f"  M{line_name}: {event_count} event{'s' if event_count > 1 else ''} → {filename}")

    (public / "tousmetros.ics").write_bytes(all_cal.to_ical())

    event_counts = {name: count for name, _, count in line_stats}
    (data_dir / "summary.md").write_text(generate_summary(by_line, dis_to_stops, dis_by_id, metro_lines, fetched_at, diff, event_counts))
    (public / "index.html").write_text(generate_index(by_line, dis_by_id, dis_to_stops, metro_lines, fetched_at))

    today = _today().isoformat()
    (public / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url>\n'
        f'    <loc>https://travauxmetro.fr/</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        f'    <changefreq>daily</changefreq>\n'
        f'    <priority>1.0</priority>\n'
        f'  </url>\n'
        f'</urlset>\n'
    )

    print(f"Done. Generated tousmetros.ics + {len(line_stats)} line file{'s' if len(line_stats) else ''}.")
