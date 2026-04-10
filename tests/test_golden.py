"""Golden-file regression test.

Runs scripts/fetch.py with a pinned PRIM fixture and a pinned timestamp, then
diffs every produced file byte-for-byte against tests/golden/.

When refactoring fetch.py, this test is your safety net: empty diff = the
refactor is provably output-equivalent.

To re-baseline intentionally (after a deliberate output change):
    rm -rf tests/golden
    uv run python scripts/fetch.py \\
        --fixture tests/fixtures/prim_raw.json \\
        --now 2026-04-10T12:00:00+02:00 \\
        --out-dir tests/golden
    # Review `git diff tests/golden/` before committing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FIXTURE_PRIM, GOLDEN, PINNED_NOW, ROOT


def _run_fetch(out_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "fetch.py"),
            "--fixture", str(FIXTURE_PRIM),
            "--now", PINNED_NOW,
            "--out-dir", str(out_dir),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    _run_fetch(out)
    return out


def _golden_files() -> list[Path]:
    return sorted(p for p in GOLDEN.rglob("*") if p.is_file())


@pytest.mark.parametrize("golden_file", _golden_files(), ids=lambda p: str(p.relative_to(GOLDEN)))
def test_golden_file_matches(generated: Path, golden_file: Path) -> None:
    rel = golden_file.relative_to(GOLDEN)
    actual = generated / rel
    assert actual.exists(), f"fetch.py did not produce {rel}"
    assert actual.read_bytes() == golden_file.read_bytes(), (
        f"{rel} differs from golden baseline.\n"
        f"  Golden:   {golden_file}\n"
        f"  Actual:   {actual}\n"
        f"Run `diff {golden_file} {actual}` to inspect."
    )


def test_no_extra_files(generated: Path) -> None:
    """fetch.py must not produce files that aren't in the golden baseline."""
    golden_rels = {p.relative_to(GOLDEN) for p in GOLDEN.rglob("*") if p.is_file()}
    actual_rels = {p.relative_to(generated) for p in generated.rglob("*") if p.is_file()}
    extras = actual_rels - golden_rels
    assert not extras, f"fetch.py produced unexpected files: {sorted(extras)}"
