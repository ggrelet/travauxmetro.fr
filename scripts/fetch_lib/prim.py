"""PRIM fetching, parsing, normalization, classification, hashing."""

import hashlib
import html
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime

import requests

from .constants import NIGHT_CUTOFF, NIGHT_STRIP_TO, PARIS_TZ, PRIM_URL


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


def dis_fingerprint(d: dict) -> list:
    """Content fingerprint for a disruption, ignoring its ID.
    Returns sorted list of [begin, end] pairs from applicationPeriods.
    Two disruptions with the same fingerprint are considered the same event
    even if PRIM re-issued them with a new UUID.
    """
    return sorted([p["begin"][:15], p["end"][:15]] for p in d.get("applicationPeriods", []))


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
