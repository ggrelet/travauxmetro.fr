"""Markdown summary generation for data/summary.md."""

from .constants import METRO_LINE_COLORS, RER_LINE_COLORS
from .html import fmt_date
from .ics import deduplicate_events, make_events
from .prim import (
    classify_disruptions,
    line_sort_key,
    parse_dt,
    period_key,
    strip_html,
)

_LINE_COLORS = {**METRO_LINE_COLORS, **RER_LINE_COLORS}


def _network_for(line_name: str) -> str:
    return "RapidTransit" if line_name in RER_LINE_COLORS else "Metro"


def _line_label(line_name: str) -> str:
    return f"RER {line_name}" if line_name in RER_LINE_COLORS else f"M{line_name}"


def generate_summary(by_line: dict, dis_to_stops: dict, dis_by_id: dict, metro_lines: dict, fetched_at: str, diff: dict | None = None, event_counts: dict | None = None) -> str:
    date_str = f"{fetched_at[8:10]}-{fetched_at[5:7]}-{fetched_at[:4]}"
    name_to_id = {l["shortName"]: lid for lid, l in metro_lines.items()}

    def badge(line_name: str) -> str:
        bg, _ = _LINE_COLORS.get(line_name, ("#888888", "#FFFFFF"))
        label = _line_label(line_name)
        # shields.io needs spaces URL-encoded
        url_label = label.replace(" ", "%20")
        return f"![{label}](https://img.shields.io/badge/-{url_label}-{bg[1:]}?style=flat)"

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
        "| Ligne | Interruptions |",
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
        normal_ids, _ = classify_disruptions(dis_ids, dis_by_id)
        network = _network_for(line_name)
        all_events = []
        for dis_id in normal_ids:
            all_events.extend(make_events(dis_by_id[dis_id], line_name, dis_to_stops[dis_id].get(line_id, []), network=network))
        available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

        for dis_id in sorted(normal_ids):
            d = dis_by_id[dis_id]
            title = d.get("title", "Interruption").strip()
            short = d.get("shortMessage", "").strip()
            message = strip_html(d.get("message", ""))
            stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []

            # Only show periods that survived deduplication
            surviving = []
            for p in d.get("applicationPeriods", []):
                key = period_key(parse_dt(p["begin"]), parse_dt(p["end"]))
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
