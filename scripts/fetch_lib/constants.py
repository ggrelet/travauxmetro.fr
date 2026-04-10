"""Shared constants, paths, and time hooks for the fetch_lib package."""

from datetime import date, datetime, time as time_type, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")


# Test hook: when set (via --now), all calls to _utc_now() / _today() return
# values derived from this fixed point, making fetch.py output deterministic.
_FAKE_NOW: datetime | None = None


def set_fake_now(dt: datetime | None) -> None:
    """Install a fake "now" for deterministic runs. Called from main()."""
    global _FAKE_NOW
    _FAKE_NOW = dt


def _utc_now() -> datetime:
    if _FAKE_NOW is not None:
        return _FAKE_NOW.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _today() -> date:
    if _FAKE_NOW is not None:
        return _FAKE_NOW.astimezone(PARIS_TZ).date()
    return date.today()


# Night service ends around 01:30–02:00, resumes around 05:00.
# Events ending before NIGHT_CUTOFF are "end of night", not start of next morning.
NIGHT_CUTOFF = time_type(5, 0)
# Night events (e.g. 22:00 → 04:30 next day) are stripped to NIGHT_STRIP_TO
# to make clear they belong to the previous evening.
NIGHT_STRIP_TO = time_type(2, 0)

ROOT = Path(__file__).parent.parent.parent

PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2"
BASE_URL = "https://travauxmetro.fr"
CONTACT_EMAIL = "contact@travauxmetro.fr"
UMAMI = '<script defer src="https://cloud.umami.is/script.js" data-website-id="ef00b128-53c5-49eb-a0e9-e4da83748a67"></script>'
FAVICON = (
    '<link rel="icon" type="image/svg+xml" href="/favicon/favicon.svg">'
    '<link rel="icon" type="image/png" sizes="96x96" href="/favicon/favicon-96x96.png">'
    '<link rel="icon" type="image/x-icon" href="/favicon/favicon.ico">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/favicon/apple-touch-icon.png">'
    '<link rel="manifest" href="/favicon/site.webmanifest">'
)

# Line names match IDFM shortName (e.g. "3B" not "3bis")
# (bg_color, text_color)
METRO_LINE_COLORS = {
    "1":  ("#FFCD00", "#000000"),
    "2":  ("#003CA6", "#FFFFFF"),
    "3":  ("#837902", "#FFFFFF"),
    "3B": ("#6EC4E8", "#000000"),
    "4":  ("#CF009E", "#FFFFFF"),
    "5":  ("#FF7E2E", "#000000"),
    "6":  ("#6ECA97", "#000000"),
    "7":  ("#FA9ABA", "#000000"),
    "7B": ("#83C491", "#000000"),
    "8":  ("#E19BDF", "#000000"),
    "9":  ("#B6BD00", "#000000"),
    "10": ("#C9910D", "#000000"),
    "11": ("#704B1C", "#FFFFFF"),
    "12": ("#007852", "#FFFFFF"),
    "13": ("#98D4E2", "#000000"),
    "14": ("#62259D", "#FFFFFF"),
}
