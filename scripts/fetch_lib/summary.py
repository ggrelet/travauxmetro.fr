"""Markdown summary generation for data/summary.md.

Renders only what changed since the last run: per-line added/removed
disruptions with date range always visible and details (stops, type,
description) collapsed inside a <details> block for cherry-picking.
"""

from .constants import METRO_LINE_COLORS, RER_LINE_COLORS
from .html import fmt_date
from .prim import line_sort_key, strip_html

_LINE_COLORS = {**METRO_LINE_COLORS, **RER_LINE_COLORS}

# Colors for +/- count badges — neither is used by any metro/RER line.
_GREEN = "28a745"  # GitHub success green
_RED = "d73a49"    # GitHub danger red


def _line_label(line_name: str) -> str:
    return f"RER {line_name}" if line_name in RER_LINE_COLORS else f"M{line_name}"


def _badge(line_name: str) -> str:
    bg, _ = _LINE_COLORS.get(line_name, ("#888888", "#FFFFFF"))
    label = _line_label(line_name)
    url_label = label.replace(" ", "%20")
    return f"![{label}](https://img.shields.io/badge/-{url_label}-{bg[1:]}?style=flat)"


def _count_badge(n: int, added: bool) -> str:
    if added:
        # %2B = '+', green
        return f"![+{n}](https://img.shields.io/badge/-%2B{n}-{_GREEN}?style=flat)"
    else:
        # %E2%88%92 = '−' (U+2212), red
        return f"![-{n}](https://img.shields.io/badge/-%E2%88%92{n}-{_RED}?style=flat)"


def _period_range(periods: list) -> str:
    if not periods:
        return ""
    return f"{fmt_date(periods[0][0])} → {fmt_date(periods[-1][1])}"


def _render_added(dis: dict, stops: list[str]) -> list[str]:
    title = dis.get("title", "Interruption").strip()
    short = dis.get("shortMessage", "").strip()
    message = strip_html(dis.get("message", ""))
    app_periods = dis.get("applicationPeriods", [])
    period_str = (
        f"{fmt_date(app_periods[0]['begin'])} → {fmt_date(app_periods[-1]['end'])}"
        if app_periods else ""
    )
    out = [f"- **{title}**" + (f" — {period_str}" if period_str else "")]

    details_parts = []
    if stops:
        details_parts.append(f"🚉 {', '.join(stops)}")
    if short and short != title:
        details_parts.append(short)
    if message and message not in (title, short):
        details_parts.append(message)

    if details_parts:
        content = "<br>".join(details_parts)
        out.append(f"  <details><summary>Détails</summary><br>{content}</details>")
    return out


def generate_summary(by_line: dict, dis_to_stops: dict, dis_by_id: dict, metro_lines: dict, fetched_at: str, diff: dict | None = None) -> str:
    date_str = f"{fetched_at[8:10]}-{fetched_at[5:7]}-{fetched_at[:4]}"
    name_to_id = {l["shortName"]: lid for lid, l in metro_lines.items()}

    lines = [f"## Travaux métro — {date_str}", ""]

    if not diff:
        lines += ["_Aucun changement depuis la dernière exécution._", ""]
    else:
        for line_name in sorted(diff.keys(), key=line_sort_key):
            d = diff[line_name]
            added = d.get("added", [])
            removed = d.get("removed", [])
            counts = []
            if added:
                counts.append(_count_badge(len(added), added=True))
            if removed:
                counts.append(_count_badge(len(removed), added=False))
            lines.append(f"### {_badge(line_name)} &nbsp;｜&nbsp; {' '.join(counts)}")
            lines.append("")
            line_id = name_to_id.get(line_name)

            if added:
                lines.append("**Ajouté**")
                lines.append("")
                for dis_id in added:
                    stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []
                    lines.extend(_render_added(dis_by_id[dis_id], stops))
                lines.append("")

            if removed:
                lines.append("**Supprimé**")
                lines.append("")
                for fp in removed:
                    lines.append(f"- {_period_range(fp)}")
                lines.append("")

    lines += [
        "---",
        "**Source :** [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)",
        "",
    ]
    return "\n".join(lines)
