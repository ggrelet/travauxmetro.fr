#!/usr/bin/env python3
"""Generate data/line-colors.html from data/line-colors.md (source of truth)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MD = ROOT / "data" / "line-colors.md"
HTML = ROOT / "data" / "line-colors.html"


def parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        if line.startswith("|") and not re.match(r"^\|[-| :]+\|$", line.strip()):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows


def extract_hex(cell: str) -> str:
    m = re.search(r"`(#[0-9a-fA-F]{6})`", cell)
    return m.group(1) if m else ""


def swatch(hex_color: str, width: int = 60) -> str:
    return (
        f'<span style="background:{hex_color};display:inline-block;'
        f'width:{width}px;height:22px;border-radius:3px;'
        f'vertical-align:middle;margin-right:.4em"></span>'
    )


# Load METRO_LINE_COLORS for text color (black/white) lookup
sys.path.insert(0, str(ROOT))
from scripts.fetch import METRO_LINE_COLORS, _GOOGLE_PALETTE
palette_by_name = {k.lower(): v for k, v in _GOOGLE_PALETTE.items()}

text = MD.read_text()
sections = re.split(r"^##\s+", text, flags=re.MULTILINE)

line_rows_md = [l for l in sections[1].splitlines() if l.startswith("|")]
palette_rows_md = [l for l in sections[2].splitlines() if l.startswith("|")]

line_table = parse_table(line_rows_md)
palette_table = parse_table(palette_rows_md)

# Build line rows (skip header)
line_html = ""
for row in line_table[1:]:
    ligne, ratp, palette_name = row
    bg = extract_hex(ratp)
    gcal_hex = palette_by_name.get(palette_name.strip().lower(), "#ccc")
    line_id = ligne.replace("M", "")
    _, fg = METRO_LINE_COLORS.get(line_id, ("#000", "#000"))
    badge = f'<span style="background:{bg};color:{fg};padding:.2em .6em;border-radius:4px;font-weight:700">{ligne}</span>'
    line_html += f"""
  <tr>
    <td>{badge}</td>
    <td>{swatch(bg)}<code>{bg}</code></td>
    <td>{swatch(gcal_hex)}<code>{gcal_hex}</code> {palette_name.strip()}</td>
  </tr>"""

# Build palette rows (skip header)
palette_html = ""
for row in palette_table[1:]:
    name, hex_cell = row
    h = extract_hex(hex_cell)
    palette_html += f"""
  <tr>
    <td>{name}</td>
    <td>{swatch(h)}<code>{h}</code></td>
  </tr>"""

html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<title>Couleurs lignes métro</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
  th, td {{ border: 1px solid #e0e0e0; padding: .4rem .75rem; text-align: left; vertical-align: middle; }}
  th {{ background: #f4f4f4; font-weight: 600; }}
  code {{ font-size: .85em; }}
  p.note {{ color: #888; font-size: .85em; }}
</style>
</head><body>
<h1>Couleurs des lignes de métro</h1>
<p class="note">Généré depuis <code>data/line-colors.md</code> — éditer le Markdown, pas ce fichier.</p>
<h2>Mapping RATP → Google Calendar</h2>
<table>
  <thead><tr><th>Ligne</th><th>RATP (iCal)</th><th>Google Calendar</th></tr></thead>
  <tbody>{line_html}</tbody>
</table>
<h2>Google Calendar palette</h2>
<table>
  <thead><tr><th>Name</th><th>Hex</th></tr></thead>
  <tbody>{palette_html}</tbody>
</table>
</body></html>"""

HTML.write_text(html)
print(f"Written → {HTML}")
