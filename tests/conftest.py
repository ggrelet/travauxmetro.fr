"""Shared test config: constants and fixtures."""
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURE_PRIM = ROOT / "tests" / "fixtures" / "prim_raw.json"
GOLDEN = ROOT / "tests" / "golden"

# Pinned timestamp the golden baseline was generated against.
# Change this only when intentionally re-baselining (then regenerate goldens).
PINNED_NOW = "2026-04-10T12:00:00+02:00"
