"""index.html generation and rendering helpers."""

from datetime import date, datetime, timedelta
from pathlib import Path

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

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Travaux Métro</title>
  <meta name="description" content="Calendrier des interruptions et travaux planifiés du métro parisien, mis à jour quotidiennement. Abonnez-vous à votre ligne.">
  <meta name="theme-color" content="#003CA6">
  <link rel="canonical" href="https://travauxmetro.fr/">
  <meta property="og:title" content="Travaux Métro">
  <meta property="og:description" content="Calendrier des interruptions et travaux planifiés du métro parisien, mis à jour quotidiennement. Abonnez-vous à votre ligne.">
  <meta property="og:url" content="https://travauxmetro.fr/">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Travaux Métro">
  <meta property="og:locale" content="fr_FR">
  <meta property="og:image" content="https://travauxmetro.fr/assets/og-image-cream.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Travaux Métro">
  <meta name="twitter:description" content="Calendrier des interruptions et travaux planifiés du métro parisien, mis à jour quotidiennement. Abonnez-vous à votre ligne.">
  <meta name="twitter:image" content="https://travauxmetro.fr/assets/og-image-cream.png">
  <link rel="sitemap" type="application/xml" href="/sitemap.xml">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "Travaux Métro Paris",
    "url": "https://travauxmetro.fr",
    "description": "Calendrier des interruptions et travaux planifiés du métro parisien, mis à jour quotidiennement. Abonnez-vous à votre ligne.",
    "applicationCategory": "UtilitiesApplication",
    "operatingSystem": "All",
    "offers": {{ "@type": "Offer", "price": "0", "priceCurrency": "EUR" }},
    "inLanguage": "fr",
    "dateModified": "{fetched_at[:10]}"
  }}
  </script>
  {FAVICON}
  {UMAMI}
  <style>
{CSS_INLINE}  </style>
</head>
<body>
  <h1 style="display:flex;align-items:center;gap:.35em;line-height:.95"><svg xmlns="http://www.w3.org/2000/svg" width="2.43em" height="2.43em" viewBox="-1.5 -1.5 27 27" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex-shrink:0"><g transform="rotate(90 12 12) translate(12 12) scale(1.1) translate(-12 -12)"><path d="M2 17 17 2"/><path d="m2 14 8 8"/><path d="m5 11 8 8"/><path d="m8 8 8 8"/><path d="m11 5 8 8"/><path d="m14 2 8 8"/><path d="M7 22 22 7"/></g><g transform="translate(12 12) scale(.6) translate(-12 -12)"><path stroke="#222" stroke-width="2.5" stroke-opacity="1" d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z"/><path stroke="#E6B800" stroke-width="1" fill="#222" d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z"/></g></svg><span>Travaux<br><span style="display:block;padding-left:.09em"><span style="color:#E6B800;text-shadow:-2px -2px 0 #222,2px -2px 0 #222,-2px 2px 0 #222,2px 2px 0 #222,0 -2px 0 #222,0 2px 0 #222,-2px 0 0 #222,2px 0 0 #222,-1px -2px 0 #222,1px -2px 0 #222,-2px -1px 0 #222,2px -1px 0 #222,-2px 1px 0 #222,2px 1px 0 #222,-1px 2px 0 #222,1px 2px 0 black;letter-spacing:+.05em">M</span>étro</span></span></h1>
  <p class="subtitle" style="margin-top:2rem">Interruptions et travaux planifiés par Île-de-France Mobilités.</br>Abonnez-vous au calendrier d'interruptions de votre ligne de métro parisien.</p>

  <div class="intro">
    Cliquez sur <strong>le fournisseur de calendrier de votre choix</strong> pour vous abonner en un clic.</br>
    Le calendrier se met à jour <strong>automatiquement</strong> lorsque de nouvelles interruptions sont prévues sur le réseau.
    <details style="margin-top:.6rem">
      <summary style="color:#888;font-weight:500">Comment ça marche ?</summary>
      <p style="margin:.5rem 0 0;font-size:.88em;color:#555">
        Un abonnement <a href="https://fr.wikipedia.org/wiki/ICalendar" target="_blank" rel="noopener" style="color:#555">iCalendar (aussi abrégé iCal)</a> est un calendrier en lecture seule hébergé sur Internet que votre application de calendrier récupère à intervale régulier.
        Les événements apparaissent directement dans votre agenda, sans compte supplémentaire à créer.
        Dès que de nouvelles interruptions sont prévues et publiées par Île-de-France Mobilités, elles se synchronisent automatiquement.
      </p>
    </details>
  </div>

  <p class="contact-hint">Une question, une suggestion, une erreur à remonter&nbsp;? <span style="white-space:nowrap">→ <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></span></p>

  {disrupted_section}
  {calm_section}

  <section>
    <h2 class="section-title">Toutes les lignes</h2>
    <p class="section-note">Un seul abonnement pour suivre toutes les interruptions du réseau en même temps.</p>
    <div class="line-row">
      <div class="line-header">
        <div class="all-badges">{all_badges}</div>
        <div class="line-vsep"></div>
        <div class="line-actions">{_sub_buttons(all_url, "all")}</div>
      </div>
    </div>
  </section>

  <footer>
    <div>Source : <a href="https://prim.iledefrance-mobilites.fr">Île-de-France Mobilités (PRIM)</a></div>
    <div><a href="https://github.com/ggrelet/travauxmetro.fr"><img src="/icons/github.svg" width="14" height="14" alt="GitHub" style="vertical-align:middle;margin-right:.25em;margin-bottom:2px">code source</a></div>
    <div>Dernière mise à jour : <span style="white-space:nowrap">{date_str} à {time_str}</span></div>
    <div>→ <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></div>
  </footer>
  <script>
{JS_INLINE}  </script>
</body>
</html>"""
