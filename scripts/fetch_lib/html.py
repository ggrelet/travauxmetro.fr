"""index.html generation and rendering helpers."""

from datetime import date, datetime, timedelta
from pathlib import Path

from babel.dates import format_date
from jinja2 import Environment, FileSystemLoader

from .constants import BASE_URL, CONTACT_EMAIL, FAVICON, METRO_LINE_COLORS, PARIS_TZ, UMAMI
from .ics import deduplicate_events, make_events
from .prim import (
    classify_disruptions,
    line_sort_key,
    normalize_period,
    parse_dt,
    period_key,
    strip_html,
)

TEMPLATES = Path(__file__).parent / "templates"

# Inlined at build time into the <style>/<script> blocks in generate_index().
# Kept as real files so editors/linters/Prettier work on them.
CSS_INLINE = (TEMPLATES / "styles.css").read_text()
JS_INLINE = (TEMPLATES / "app.js").read_text()

# Autoescape is intentionally off: every variable we pass to the template is
# already trusted HTML (our own markup, or PRIM text that went through
# strip_html).
_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=False,
    keep_trailing_newline=False,
)


def fmt_dt(s: str) -> str:
    """YYYYMMDDTHHmmss → '25-04-2026 06:00'"""
    dt = datetime.strptime(s, "%Y%m%dT%H%M%S")
    return f"{dt.day:02d}-{dt.month:02d}-{dt.year} {dt.hour:02d}:{dt.minute:02d}"


def fmt_date(s: str) -> str:
    """YYYYMMDD... → 'DD-MM-YYYY'"""
    return f"{s[6:8]}-{s[4:6]}-{s[:4]}"


def fmt_period_display(p: dict) -> str:
    """Format a PRIM period dict using normalized bounds."""
    def fdate(d: date) -> str:
        return format_date(d, "EEE d MMMM", locale="fr")

    def fdt(dt: datetime) -> str:
        return f"{format_date(dt, 'EEE d MMMM', locale='fr')} {dt.hour:02d}:{dt.minute:02d}"

    ns, ne, is_allday = normalize_period(parse_dt(p["begin"]), parse_dt(p["end"]))
    if is_allday:
        last = ne - timedelta(days=1)
        return fdate(ns) if ns == last else f"{fdate(ns)} → {fdate(last)}"
    return f"{fdt(ns)} → {fdt(ne)}"


def _line_view(line_name: str, bg: str, fg: str) -> dict:
    """Common URL variants and label HTML for one line (independent of disruption state)."""
    ics_url = f"{BASE_URL}/ligne-{line_name}.ics"
    webcal_url = ics_url.replace("https://", "webcal://")
    encoded_url = ics_url.replace("://", "%3A%2F%2F").replace("/", "%2F")
    gcal_cid = webcal_url.replace("://", "%3A%2F%2F").replace("/", "%2F")
    if line_name.endswith("B"):
        label_html = f'{line_name[:-1]}<span style="font-size:.42em;letter-spacing:-.02em">bis</span>'
    else:
        label_html = line_name
    return {
        "name": line_name,
        "bg": bg,
        "fg": fg,
        "label_html": label_html,
        "ics_url": ics_url,
        "webcal_url": webcal_url,
        "encoded_url": encoded_url,
        "gcal_cid": gcal_cid,
    }


def _build_cards(
    line_name: str,
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
) -> list[dict]:
    """Return the card view-models for a disrupted line (may be empty after filtering)."""
    line_id = next((lid for lid, l in metro_lines.items() if l["shortName"] == line_name), None)
    all_ids = by_line.get(line_name, set())
    normal_ids, _ = classify_disruptions(all_ids, dis_by_id)

    all_events = []
    for dis_id in normal_ids:
        stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []
        all_events.extend(make_events(dis_by_id[dis_id], line_name, stops))
    available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

    cards = []
    for dis_id in sorted(normal_ids):
        d = dis_by_id[dis_id]
        title = d.get("title", "").strip()
        short = d.get("shortMessage", "").strip()
        message = strip_html(d.get("message", ""))
        stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []

        surviving = []
        for p in d.get("applicationPeriods", []):
            key = period_key(parse_dt(p["begin"]), parse_dt(p["end"]))
            if key in available:
                surviving.append(p)
                available.discard(key)

        if not surviving:
            continue

        cards.append({
            "title": title or short or "Interruption",
            "periods": [fmt_period_display(p) for p in surviving],
            "stops": ", ".join(stops),
            "message": message,
        })
    return cards


def generate_index(
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
    fetched_at: str,
) -> str:
    fetched_dt = datetime.fromisoformat(fetched_at).astimezone(PARIS_TZ)
    date_str = format_date(fetched_dt, "EEEE d MMMM", locale="fr")
    time_str = fetched_dt.strftime("%H:%M")

    all_lines = []
    disrupted_lines = []
    calm_lines = []
    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, fg = METRO_LINE_COLORS[line_name]
        view = _line_view(line_name, bg, fg)
        all_lines.append(view)

        if by_line.get(line_name):
            view["cards"] = _build_cards(line_name, by_line, dis_by_id, dis_to_stops, metro_lines)
            n = len(view["cards"])
            view["card_count"] = n
            view["dialog_id"] = f"dis-{line_name}"
            view["label_text"] = f"{n} interruption{'s' if n > 1 else ''} prévue{'s' if n > 1 else ''}"
            disrupted_lines.append(view)
        else:
            calm_lines.append(view)

    all_url = f"{BASE_URL}/tousmetros.ics"
    all_sub = {
        "name": "all",
        "ics_url": all_url,
        "webcal_url": all_url.replace("https://", "webcal://"),
        "encoded_url": all_url.replace("://", "%3A%2F%2F").replace("/", "%2F"),
        "gcal_cid": all_url.replace("https://", "webcal://").replace("://", "%3A%2F%2F").replace("/", "%2F"),
    }

    return _ENV.get_template("index.html.j2").render(
        fetched_at_date=fetched_at[:10],
        favicon=FAVICON,
        umami=UMAMI,
        css_inline=CSS_INLINE,
        js_inline=JS_INLINE,
        contact_email=CONTACT_EMAIL,
        disrupted_lines=disrupted_lines,
        calm_lines=calm_lines,
        all_lines=all_lines,
        all_sub=all_sub,
        date_str=date_str,
        time_str=time_str,
    )
