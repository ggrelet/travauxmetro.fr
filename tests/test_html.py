"""Unit tests for html.py formatting helpers."""
from __future__ import annotations

import pytest

from fetch_lib.html import fmt_period_display


@pytest.mark.parametrize("begin,end,expected", [
    # All-day, single day: midnight to midnight next day
    ("20260413T000000", "20260414T000000", "lun. 13 avril"),
    # All-day range: Mon 00:00 → Thu 04:30 → rendered as Mon → Wed (end - 1 day)
    ("20260413T000000", "20260416T043000", "lun. 13 avril → mer. 15 avril"),
    # Overnight night-strip: 22:00 → 04:30 next day becomes 22:00 → 02:00
    ("20260410T220000", "20260411T043000", "ven. 10 avril 22:00 → sam. 11 avril 02:00"),
    # Daytime pass-through: neither all-day nor night-strip
    ("20260410T100000", "20260410T180000", "ven. 10 avril 10:00 → ven. 10 avril 18:00"),
])
def test_fmt_period_display(begin: str, end: str, expected: str) -> None:
    assert fmt_period_display({"begin": begin, "end": end}) == expected
