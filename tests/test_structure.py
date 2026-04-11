"""Structural tests — survive cosmetic reformatting.

These assert that the *meaning* of the output is correct, not its exact bytes.
They're the complement to test_golden.py: golden catches byte drift, structure
catches "I changed the layout but accidentally dropped a metro line".
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from icalendar import Calendar

from conftest import FIXTURE_PRIM, PINNED_NOW, ROOT

METRO_LINES = ["1", "2", "3", "3B", "4", "5", "6", "7", "7B",
               "8", "9", "10", "11", "12", "13", "14"]


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fetch.py"),
         "--fixture", str(FIXTURE_PRIM),
         "--now", PINNED_NOW,
         "--out-dir", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def test_index_html_has_all_lines(generated: Path) -> None:
    html = (generated / "public" / "index.html").read_text()
    for line in METRO_LINES:
        # Every line should appear as a badge (bg-colored circle)
        assert f"ligne-{line}.ics" in html, f"Line {line} missing from index.html"


def test_index_html_no_unescaped_braces(generated: Path) -> None:
    """Catches f-string escaping regressions ({{ }} leaking into output)."""
    html = (generated / "public" / "index.html").read_text()
    # Allow CSS calc() etc. but no double-brace runs
    assert "{{" not in html, "Unescaped {{ in index.html — f-string regression"
    assert "}}" not in html, "Unescaped }} in index.html — f-string regression"


def test_index_html_has_json_ld(generated: Path) -> None:
    html = (generated / "public" / "index.html").read_text()
    assert 'application/ld+json' in html
    assert '"dateModified"' in html


@pytest.mark.parametrize("line", METRO_LINES)
def test_ics_parses(generated: Path, line: str) -> None:
    path = generated / "public" / f"ligne-{line}.ics"
    assert path.exists(), f"Missing {path.name}"
    cal = Calendar.from_ical(path.read_bytes())
    # Must at least have the calendar metadata
    assert cal.get("X-WR-CALNAME") or cal.get("PRODID")


def test_tousmetros_ics_parses(generated: Path) -> None:
    cal = Calendar.from_ical((generated / "public" / "tousmetros.ics").read_bytes())
    assert cal.get("PRODID")


def test_sitemap_has_lastmod(generated: Path) -> None:
    xml = (generated / "public" / "sitemap.xml").read_text()
    assert "<lastmod>" in xml
    # Pinned --now is 2026-04-10T12:00:00+02:00 → date is 2026-04-10
    assert "2026-04-10" in xml


def test_summary_has_header_and_source(generated: Path) -> None:
    md = (generated / "data" / "summary.md").read_text()
    assert "Travaux métro" in md
    assert "PRIM" in md


def test_snapshot_json_has_fetched_at(generated: Path) -> None:
    import json
    snap = json.loads((generated / "data" / "snapshot.json").read_text())
    assert snap["fetched_at"].startswith("2026-04-10T10:00:00")  # UTC equivalent of 12:00 Paris
    assert isinstance(snap["disruptions"], list)
