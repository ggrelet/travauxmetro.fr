"""Live smoke checks run against today's generated output.

Unlike test_structure.py / test_golden.py (which pin a fixture and date),
these validate the real files in public/ and data/snapshot.json after a
live scripts/fetch.py run. They are marked `live` and deselected by
default so `pytest tests/` stays hermetic — CI's update workflow opts in
with `pytest -m live`.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest
from icalendar import Calendar

from conftest import ROOT

pytestmark = pytest.mark.live

PUBLIC = ROOT / "public"
SNAPSHOT = ROOT / "data" / "snapshot.json"

METRO_LINES = ["1", "2", "3", "3B", "4", "5", "6", "7", "7B",
               "8", "9", "10", "11", "12", "13", "14"]

MIN_RATIO = 0.9


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text())


def test_disruptions_nonempty(snapshot: dict) -> None:
    assert len(snapshot.get("disruptions", [])) > 0, "snapshot.json has zero disruptions"


@pytest.mark.parametrize("line", METRO_LINES)
def test_ics_parses(line: str) -> None:
    path = PUBLIC / f"ligne-{line}.ics"
    assert path.exists(), f"missing {path.name}"
    Calendar.from_ical(path.read_bytes())


@pytest.mark.parametrize("filename", ["tousmetros.ics", "tousrer.ics", "toustram.ics"])
def test_all_network_ics_has_events(filename: str) -> None:
    """Guard against a deploy that drops all events for a network."""
    cal = Calendar.from_ical((PUBLIC / filename).read_bytes())
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert events, f"{filename} has zero VEVENTs"


def test_sitemap_has_today() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    xml = (PUBLIC / "sitemap.xml").read_text()
    assert today in xml, f"sitemap missing today's date {today}"


def test_disruption_count_not_collapsed(snapshot: dict) -> None:
    try:
        old_blob = subprocess.check_output(
            ["git", "show", "HEAD:data/snapshot.json"],
            cwd=ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        pytest.skip("no prior snapshot in HEAD")
    old_n = len(json.loads(old_blob).get("disruptions", []))
    new_n = len(snapshot.get("disruptions", []))
    if old_n == 0:
        pytest.skip("prior snapshot was empty")
    ratio = new_n / old_n
    assert ratio >= MIN_RATIO, (
        f"disruptions collapsed: {old_n} -> {new_n} (ratio {ratio:.2f} < {MIN_RATIO})"
    )
