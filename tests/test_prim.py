"""Unit tests for prim.py pure helpers."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from fetch_lib.constants import PARIS_TZ
from fetch_lib.prim import normalize_period


def _dt(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=PARIS_TZ)


class TestNormalizePeriodAllDay:
    """end < NIGHT_CUTOFF (05:00) AND (start < NIGHT_CUTOFF OR span > 1 day)
    → returned as (date, date, True), end exclusive."""

    def test_single_day_midnight_to_midnight(self):
        ns, ne, is_allday = normalize_period(_dt(2026, 4, 10), _dt(2026, 4, 11))
        assert (ns, ne, is_allday) == (date(2026, 4, 10), date(2026, 4, 11), True)

    def test_multi_day_midnight_to_early_morning(self):
        # Mon 00:00 → Thu 04:30 spans > 1 day and ends before cutoff
        ns, ne, is_allday = normalize_period(_dt(2026, 4, 10), _dt(2026, 4, 13, 4, 30))
        assert (ns, ne, is_allday) == (date(2026, 4, 10), date(2026, 4, 13), True)

    def test_end_at_cutoff_exact_is_not_allday(self):
        # end == NIGHT_CUTOFF (05:00) is NOT before it → not all-day
        _, _, is_allday = normalize_period(_dt(2026, 4, 10), _dt(2026, 4, 11, 5, 0))
        assert is_allday is False


class TestNormalizePeriodNightStrip:
    """start >= NIGHT_CUTOFF AND span == 1 day AND end < NIGHT_CUTOFF
    → end stripped to NIGHT_STRIP_TO (02:00), kept as datetime."""

    def test_overnight_22_to_0430_stripped_to_02(self):
        ns, ne, is_allday = normalize_period(
            _dt(2026, 4, 10, 22, 0), _dt(2026, 4, 11, 4, 30),
        )
        assert is_allday is False
        assert ns == _dt(2026, 4, 10, 22, 0)
        assert ne == _dt(2026, 4, 11, 2, 0)

    def test_overnight_start_exactly_at_cutoff(self):
        # start == 05:00 (NIGHT_CUTOFF), span 1 day, end before cutoff
        ns, ne, is_allday = normalize_period(
            _dt(2026, 4, 10, 5, 0), _dt(2026, 4, 11, 3, 0),
        )
        assert is_allday is False
        assert ne == _dt(2026, 4, 11, 2, 0)


class TestNormalizePeriodAsIs:
    """Anything that isn't all-day or night-strip passes through untouched."""

    def test_midday_to_midday_same_day(self):
        a, b = _dt(2026, 4, 10, 10, 0), _dt(2026, 4, 10, 18, 0)
        assert normalize_period(a, b) == (a, b, False)

    def test_end_at_noon_next_day(self):
        # end >= NIGHT_CUTOFF → falls through
        a, b = _dt(2026, 4, 10, 22, 0), _dt(2026, 4, 11, 12, 0)
        assert normalize_period(a, b) == (a, b, False)

    def test_daytime_spanning_midnight_not_allday(self):
        # 10:00 → 23:00 same day, neither end-of-night nor overnight
        a, b = _dt(2026, 4, 10, 10, 0), _dt(2026, 4, 10, 23, 0)
        assert normalize_period(a, b) == (a, b, False)


@pytest.mark.parametrize("start,end,expected_allday", [
    (_dt(2026, 4, 10), _dt(2026, 4, 11), True),                    # midnight to midnight
    (_dt(2026, 4, 10), _dt(2026, 4, 11, 4, 30), True),             # midnight to early AM
    (_dt(2026, 4, 10, 22), _dt(2026, 4, 11, 4, 30), False),        # night strip
    (_dt(2026, 4, 10, 10), _dt(2026, 4, 10, 18), False),           # daytime
])
def test_allday_flag(start, end, expected_allday):
    _, _, is_allday = normalize_period(start, end)
    assert is_allday is expected_allday
