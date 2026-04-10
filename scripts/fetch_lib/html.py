"""index.html generation and rendering helpers."""

from datetime import date, datetime, timedelta
from pathlib import Path

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
# strip_html). If/when we move per-row rendering into the template, flip this.
_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=False,
    keep_trailing_newline=False,
)


_WEBCAL_ICON = '<img src="/icons/apple.svg" width="16" height="16" alt="" style="margin-right:.35em;flex-shrink:0">'
_GCAL_ICON = '<img src="/icons/googlecalendar.svg" width="15" height="15" alt="" style="margin-right:.35em;flex-shrink:0">'
_OUTLOOK_ICON = '<img src="/icons/outlook.svg" width="16" height="16" alt="" style="margin-right:.35em;flex-shrink:0">'
_O365_ICON = '<img src="/icons/office365.svg" width="15" height="15" alt="" style="margin-right:.35em;flex-shrink:0">'
_COPY_ICON = '<img src="/icons/copy.svg" width="14" height="14" alt="" style="margin-right:.35em;flex-shrink:0">'


def _sub_buttons(full_url: str, line: str) -> str:
    webcal_url = full_url.replace("https://", "webcal://")
    encoded_https = full_url.replace("://", "%3A%2F%2F").replace("/", "%2F")
    gcal_url = f"https://calendar.google.com/calendar/render?cid={webcal_url.replace('://', '%3A%2F%2F').replace('/', '%2F')}"
    outlook_url = f"https://outlook.live.com/calendar/0/addfromweb?url={encoded_https}"
    o365_url = f"https://outlook.office.com/calendar/addfromweb?url={encoded_https}"
    return (
        f'<a class="sub-btn google" href="{gcal_url}" target="_blank" rel="noopener" data-umami-event="subscribe-google" data-umami-event-line="{line}">{_GCAL_ICON}Google Calendar</a>'
        f'<a class="sub-btn webcal" href="{webcal_url}" data-umami-event="subscribe-webcal" data-umami-event-line="{line}">{_WEBCAL_ICON}iCal / webcal</a>'
        f'<a class="sub-btn outlook" href="{outlook_url}" target="_blank" rel="noopener" data-umami-event="subscribe-outlook" data-umami-event-line="{line}">{_OUTLOOK_ICON}Outlook</a>'
        f'<a class="sub-btn o365" href="{o365_url}" target="_blank" rel="noopener" data-umami-event="subscribe-o365" data-umami-event-line="{line}">{_O365_ICON}Office 365</a>'
        f'<button class="sub-btn copy" onclick="copyUrl(\'{full_url}\',this)" data-umami-event="copy-url" data-umami-event-line="{line}">{_COPY_ICON}Copier le lien</button>'
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
    _JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    _MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
             "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

    def fdate(d: date) -> str:
        return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]}"

    def fdt(dt: datetime) -> str:
        return f"{_JOURS[dt.weekday()]} {dt.day} {_MOIS[dt.month - 1]} {dt.hour:02d}:{dt.minute:02d}"

    ns, ne, is_allday = normalize_period(parse_dt(p["begin"]), parse_dt(p["end"]))
    if is_allday:
        last = ne - timedelta(days=1)
        return fdate(ns) if ns == last else f"{fdate(ns)} → {fdate(last)}"
    return f"{fdt(ns)} → {fdt(ne)}"


def _line_disruption_html(
    line_name: str,
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
) -> str:
    """Return the disruption details block (accordion or quiet note) for one line."""
    line_id = next((lid for lid, l in metro_lines.items() if l["shortName"] == line_name), None)
    all_ids = by_line.get(line_name, set())
    normal_ids, _ = classify_disruptions(all_ids, dis_by_id)

    all_events = []
    for dis_id in normal_ids:
        stops = dis_to_stops[dis_id].get(line_id, []) if line_id else []
        all_events.extend(make_events(dis_by_id[dis_id], line_name, stops))
    available = {(e.get("dtstart").dt, e.get("dtend").dt) for e in deduplicate_events(all_events)}

    notes_html = ""

    cards = ""
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

        periods_html = "".join(
            f'<div class="period">📅 {fmt_period_display(p)}</div>'
            for p in surviving
        )
        stops_html = f'<div class="stops"><img src="/favicon/favicon.svg" width="18" height="18" alt="" style="vertical-align:-4px;margin-right:.25em">{", ".join(stops)}</div>' if stops else ""
        message_html = f'<div class="message">{message}</div>' if message else ""

        cards += f"""
          <div class="dis-card">
            <div class="card-title">{title or short or "Interruption"}</div>
            {periods_html}{stops_html}{message_html}
          </div>"""

    card_count = cards.count('<div class="dis-card">')
    if card_count == 0:
        return '<p class="quiet">Aucune interruption prévue, mais cela pourrait arriver dans le futur. Abonnez-vous pour ne pas les manquer.</p>'

    label = f"{card_count} interruption{'s' if card_count > 1 else ''} prévue{'s' if card_count > 1 else ''}"
    dialog_id = f"dis-{line_name}"
    return f"""<button class="dis-btn" data-dialog="{dialog_id}" data-umami-event="accordion-open" data-umami-event-line="{line_name}"><span style="font-size:.8em">▶</span> {label}</button>
    <dialog id="{dialog_id}" class="dis-dialog">
      <div class="dis-dialog-header">
        <span class="badge" style="background:{METRO_LINE_COLORS[line_name][0]};color:{METRO_LINE_COLORS[line_name][1]};width:2rem;height:2rem;font-size:1.2rem;flex-shrink:0">{line_name[:-1] + '<span style="font-size:.42em;letter-spacing:-.02em">bis</span>' if line_name.endswith("B") else line_name}</span>
        <span class="dis-dialog-subtitle" style="margin:0;flex:1">{label}</span>
        <button class="dis-close" autofocus onclick="this.closest('dialog').close()">✕</button>
      </div>
      <div class="dis-dialog-body">{notes_html}<div class="cards">{cards}</div></div>
    </dialog>"""


def generate_index(
    by_line: dict,
    dis_by_id: dict,
    dis_to_stops: dict,
    metro_lines: dict,
    fetched_at: str,
) -> str:
    all_url = f"{BASE_URL}/tousmetros.ics"
    fetched_dt = datetime.fromisoformat(fetched_at).astimezone(PARIS_TZ)
    _JOURS_FULL = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    _MOIS_FULL = ["janvier", "février", "mars", "avril", "mai", "juin",
                  "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    date_str = f"{_JOURS_FULL[fetched_dt.weekday()]} {fetched_dt.day} {_MOIS_FULL[fetched_dt.month - 1]}"
    time_str = fetched_dt.strftime("%H:%M")

    disrupted_rows = ""
    calm_rows = ""
    for line_name in sorted(METRO_LINE_COLORS.keys(), key=line_sort_key):
        bg, fg = METRO_LINE_COLORS[line_name]
        full_url = f"{BASE_URL}/ligne-{line_name}.ics"
        label = f'{line_name[:-1]}<span style="font-size:.42em;letter-spacing:-.02em">bis</span>' if line_name.endswith("B") else line_name
        badge = f'<span class="badge" style="background:{bg};color:{fg}">{label}</span>'
        if by_line.get(line_name):
            dis_html = _line_disruption_html(line_name, by_line, dis_by_id, dis_to_stops, metro_lines)
            disrupted_rows += f"""
    <div class="line-row" data-line="{line_name}">
      <div class="line-header">
        {badge}
        <div class="line-vsep"></div>
        <div class="line-actions">{_sub_buttons(full_url, line_name)}</div>
      </div>
      {dis_html}
    </div>"""
        else:
            calm_rows += f"""
    <div class="line-row">
      <div class="line-header">
        {badge}
        <div class="line-vsep"></div>
        <div class="line-actions">{_sub_buttons(full_url, line_name)}</div>
      </div>
    </div>"""

    def _badge_label(n: str) -> str:
        return f'{n[:-1]}<span style="font-size:.42em;letter-spacing:-.02em">bis</span>' if n.endswith("B") else n
    all_badges = " ".join(
        f'<span class="badge" style="background:{bg};color:{fg}">{_badge_label(n)}</span>'
        for n, (bg, fg) in sorted(METRO_LINE_COLORS.items(), key=lambda x: line_sort_key(x[0]))
    )

    disrupted_section = f"""
  <section>
    <h2 class="section-title">Lignes interrompues</h2>
    <p class="section-note">Île-de-France Mobilités a prévu des interruptions dues aux travaux sur ces lignes.</p>
    <div class="lines-grid">{disrupted_rows}</div>
  </section>""" if disrupted_rows else '<p class="quiet" style="margin-bottom:1.5rem">Aucune interruption prévue sur le réseau.</p>'

    calm_section = f"""
  <section>
    <h2 class="section-title">Autres lignes</h2>
    <p class="section-note">Aucune interruption prévue sur ces lignes. Abonnez-vous pour être notifié automatiquement si cela change.</p>
    <div class="lines-grid">{calm_rows}</div>
  </section>""" if calm_rows else ""

    return _ENV.get_template("index.html.j2").render(
        fetched_at_date=fetched_at[:10],
        favicon=FAVICON,
        umami=UMAMI,
        css_inline=CSS_INLINE,
        js_inline=JS_INLINE,
        contact_email=CONTACT_EMAIL,
        disrupted_section=disrupted_section,
        calm_section=calm_section,
        all_badges=all_badges,
        sub_buttons_all=_sub_buttons(all_url, "all"),
        date_str=date_str,
        time_str=time_str,
    )
