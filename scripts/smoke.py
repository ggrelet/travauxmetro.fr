#!/usr/bin/env python3
"""Post-fetch sanity checks for the daily update workflow.

Run after scripts/fetch.py against live data. Exits non-zero if today's
output looks wrong so auto-merge is blocked.

Checks:
- data/snapshot.json has disruptions
- all 16 public/ligne-*.ics files parse
- public/sitemap.xml contains today's date
- disruption count vs HEAD snapshot hasn't collapsed (ratio >= 0.5)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
SNAPSHOT = ROOT / "data" / "snapshot.json"

METRO_LINES = ["1", "2", "3", "3B", "4", "5", "6", "7", "7B",
               "8", "9", "10", "11", "12", "13", "14"]

MIN_RATIO = 0.5


FAILURES: list[str] = []


def fail(msg: str) -> None:
    print(f"[smoke] FAIL: {msg}", file=sys.stderr)
    FAILURES.append(msg)


def check_disruptions_nonempty() -> int:
    data = json.loads(SNAPSHOT.read_text())
    n = len(data.get("disruptions", []))
    print(f"[smoke] disruptions: {n}")
    if n == 0:
        fail("snapshot.json has zero disruptions")
    return n


def check_ics_parse() -> None:
    for line in METRO_LINES:
        p = PUBLIC / f"ligne-{line}.ics"
        if not p.exists():
            fail(f"missing {p.name}")
        try:
            Calendar.from_ical(p.read_bytes())
        except Exception as e:
            fail(f"{p.name} does not parse: {e}")
    print(f"[smoke] all {len(METRO_LINES)} .ics files parse")


def check_sitemap_today() -> None:
    xml = (PUBLIC / "sitemap.xml").read_text()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today not in xml:
        fail(f"sitemap missing today's date {today}")
    print(f"[smoke] sitemap has {today}")


def check_diff_not_catastrophic(new_n: int) -> None:
    try:
        old_blob = subprocess.check_output(
            ["git", "show", "HEAD:data/snapshot.json"],
            cwd=ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        print("[smoke] no prior snapshot in HEAD, skipping diff check")
        return
    old_n = len(json.loads(old_blob).get("disruptions", []))
    if old_n == 0:
        return
    ratio = new_n / old_n
    if ratio < MIN_RATIO:
        fail(f"disruptions collapsed: {old_n} -> {new_n} (ratio {ratio:.2f} < {MIN_RATIO})")
    print(f"[smoke] disruption count {old_n} -> {new_n} (ratio {ratio:.2f})")


def main() -> None:
    n = check_disruptions_nonempty()
    check_ics_parse()
    check_sitemap_today()
    check_diff_not_catastrophic(n)
    if FAILURES:
        print(f"[smoke] {len(FAILURES)} check(s) failed", file=sys.stderr)
        sys.exit(1)
    print("[smoke] all checks passed")


if __name__ == "__main__":
    main()
