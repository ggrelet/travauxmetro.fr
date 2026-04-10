# Journal — Refactor safety net

> This file tracks the in-progress work on adding a test safety net before
> tackling the 9 proposed refactors. Append as you go; don't rewrite history.

## 2026-04-10 — Session 1: golden-file safety net installed ✅

**Goal:** before touching any of the 9 refactor suggestions (see bottom of this
file), install a test harness that can prove any refactor preserves output
byte-for-byte. If the refactor is a pure reorganisation, the test is an empty
diff. If the refactor intentionally changes output, the diff is the review.

### What was done

1. **Added test hooks to `scripts/fetch.py`** so the script is deterministic
   and offline-runnable:
   - `--fixture PATH` — load raw PRIM JSON from disk instead of hitting the API
   - `--now ISO` — override `datetime.now()` and `date.today()`
   - `--out-dir PATH` — write all outputs under a given directory (instead of
     `public/` and `data/`), creating `public/` and `data/` subdirs
   - `--save-raw PATH` — fetch the raw PRIM response, save it, exit. Used once
     to bootstrap the fixture.
   - A module-level `_FAKE_NOW` + `_utc_now()` / `_today()` helpers back the
     `--now` flag. Three prod sites updated to use them: `make_events` dtstamp,
     `fetched_at` in `main()`, and the sitemap `lastmod`.

2. **Fixed three latent non-determinism bugs in `fetch.py`** uncovered while
   setting up the test. These were real bugs — every `fetch.py` run produced
   slightly different ICS bytes because Python's `set` iteration order is
   randomised across processes. Fixes:
   - `sorted(ids)` when building `new_fps_by_line` (affects `by_line.json`)
   - `sorted(normal_ids)` when iterating for ICS event generation (affects
     `ligne-*.ics` and `tousmetros.ics`)
   - `json.dumps(..., sort_keys=True)` on `by_line.json` (dict key order is
     set-iteration-dependent)

   **Prod side-effect:** the next real `fetch.py` run will produce a
   one-time "re-ordering" diff vs. what's currently committed in `public/`
   and `data/`. The `content_hash` skip mechanism means this won't trigger
   until PRIM data actually changes. When it happens, the daily update PR
   will show both the real data diff AND the ordering churn — merge it once,
   and every subsequent diff is clean forever.

3. **Bootstrapped the fixture:**
   - `tests/fixtures/prim_raw.json` — 1.6 MB raw PRIM response captured via
     `uv run python scripts/fetch.py --save-raw tests/fixtures/prim_raw.json`
   - Pinned `--now` = `2026-04-10T12:00:00+02:00` (see `tests/conftest.py`)

4. **Generated the golden baseline** in `tests/golden/` by running fetch.py
   with the fixture + pinned now + `--out-dir tests/golden`. Verified
   byte-reproducible: two back-to-back runs produce identical trees.
   Contents: 16 `ligne-*.ics`, `tousmetros.ics`, `index.html`, `sitemap.xml`,
   and `data/{by_line.json, snapshot.json, summary.md, disruptions_hash.txt}`.

5. **Wrote tests:**
   - `tests/test_golden.py` — parametrised byte-diff of every golden file.
     23 assertions (one per file) + `test_no_extra_files`.
   - `tests/test_structure.py` — 23 semantic assertions that survive cosmetic
     reformatting: all 16 lines present, every ICS parses via `icalendar`,
     no unescaped `{{ }}`, JSON-LD present, sitemap `lastmod` present, summary
     has the expected headings, `snapshot.json` has the right `fetched_at`.
   - `tests/conftest.py` — shared constants (`ROOT`, `FIXTURE_PRIM`, `GOLDEN`,
     `PINNED_NOW`).

6. **Wired pytest** in `pyproject.toml` as a dev dependency and configured
   `testpaths = ["tests"]` + `pythonpath = ["tests"]` so `conftest` imports work.

### Current state

```
$ uv run pytest tests/
47 passed in 0.45s
```

- `scripts/fetch.py` — modified, real behavior unchanged when run with no args
- `pyproject.toml` — pytest added as dev dep
- `uv.lock` — updated
- `tests/` — new, untracked

**Nothing committed yet.** `public/` and `data/` in the repo are untouched.

### How to run the tests

```bash
uv run pytest tests/                      # full suite, ~0.5s
uv run pytest tests/test_golden.py -v     # just the byte diff
uv run pytest tests/test_structure.py -v  # just the structural checks
```

### How to re-baseline the golden (when you change output on purpose)

```bash
rm -rf tests/golden
uv run python scripts/fetch.py \
    --fixture tests/fixtures/prim_raw.json \
    --now 2026-04-10T12:00:00+02:00 \
    --out-dir tests/golden
git diff tests/golden/    # review every byte that changed
uv run pytest tests/      # should be green again
```

### How to refresh the fixture (e.g. to pick up new PRIM schema changes)

```bash
uv run python scripts/fetch.py --save-raw tests/fixtures/prim_raw.json
# Then re-baseline the golden (block above).
```

---

## 2026-04-10 — Session 2: refactors #3 and #1 ✅

### #3 — `--force` flag (done)

- Added `--force` to the argparse in `scripts/fetch.py`. When set, bypasses the
  `content_hash` skip check and regenerates all files.
- Updated `.github/workflows/update.yml` to pass `--force` via an `$ARGS`
  variable when `inputs.force == true` (instead of the old
  `rm -f data/disruptions_hash.txt` dance).
- Updated the `feedback_html_generation.md` memory to recommend
  `uv run python scripts/fetch.py --force` instead of the `mv` workaround.
- Tests: 47/47 green.

### #1 — Extract CSS and JS to real files (done)

- Created `scripts/templates/styles.css` (63 lines) and
  `scripts/templates/app.js` (59 lines), unescaping all the `{{`/`}}` noise
  that used to be required by the f-string.
- Added top-of-file loads in `fetch.py`:
  ```python
  TEMPLATES = Path(__file__).parent / "templates"
  CSS_INLINE = (TEMPLATES / "styles.css").read_text()
  JS_INLINE = (TEMPLATES / "app.js").read_text()
  ```
- Replaced the two big blocks inside `generate_index()` with
  `{CSS_INLINE}` and `{JS_INLINE}` interpolations — so the HTML stays
  a single self-contained file at serve time, but the source is editable.
- `scripts/fetch.py` shrank from 956 → 887 lines; the removed lines are now
  in real `.css` and `.js` files where Prettier/linters/editors can do
  their job.
- **Tests: 47/47 green — zero-byte golden diff.** The refactor is provably
  output-equivalent. The safety net earned its keep on its first outing.

### Current state

```
$ uv run pytest tests/
47 passed in 0.61s

$ git status --porcelain
 M .github/workflows/update.yml
 M pyproject.toml
 M scripts/fetch.py
 M uv.lock
?? JOURNAL.md
?? scripts/templates/
?? tests/
```

Still nothing committed. Suggested commit split for tomorrow:

1. `chore(test): add golden-file safety net + fix fetch.py determinism bugs`
   — `scripts/fetch.py` (flags + determinism fixes), `pyproject.toml`,
   `uv.lock`, `tests/` (new), `JOURNAL.md` (new)
2. `refactor: add --force flag, retire hash-file workaround`
   — `scripts/fetch.py` (--force), `.github/workflows/update.yml`
3. `refactor: extract inline CSS and JS from fetch.py`
   — `scripts/fetch.py` (CSS/JS replaced with interpolations),
   `scripts/templates/` (new)

Or: squash (1) + (2) + (3) into one `chore: refactor fetch.py safety net`
commit. Your call.

---

## Next session — where to pick up

### Immediate next steps (pick one)

- [ ] **Commit the safety net.** Suggested message:
  `chore(test): add golden-file safety net + fix fetch.py determinism bugs`.
  Files: `scripts/fetch.py`, `pyproject.toml`, `uv.lock`, `tests/` (new).
  Don't forget `tests/fixtures/prim_raw.json` — it's 1.6 MB but committing
  it is intentional (reproducibility).
- [ ] **Decide whether to commit `tests/fixtures/prim_raw.json` to the repo or
  store it elsewhere.** It's 1.6 MB of public data. Options:
  1. Commit as-is (simplest, what we've done locally)
  2. `.gitignore` it and document the bootstrap command
  3. Store it with Git LFS
  Recommendation: commit it. 1.6 MB is fine; reproducibility is worth more.

### The 9 refactors (from the critical review earlier today)

Each of these can now be attempted with confidence: run the test after your
change and either see an empty diff (behavior preserved) or a reviewable diff
(behavior intentionally changed).

| # | Change | Effort | Payoff |
|---|--------|--------|--------|
| 1 | Extract CSS/JS to real files, inline at build | S | **DONE ✅** |
| 2 | Jinja2 template for index.html | M | Huge (bug class eliminated) |
| 3 | Add `--force` flag, remove mv-dance | XS | **DONE ✅** |
| 4 | Golden-file test + period normalisation tests | S | **DONE ✅** |
| 5 | Split fetch.py into a package | M | Medium |
| 6 | Stop committing generated HTML, build in CI | M | Medium |
| 7 | `babel.dates` for French formatting | XS | Low |
| 8 | Fix Umami Worker `WEBSITE_ID` placeholder | XS | High if telemetry matters |
| 9 | Dedupe constants (email, duplicated CSS `a` rule) | XS | Low |

Suggested order for the next session:
1. **#3** (add `--force`) — trivial, unblocks #6 and cleans the memory rule
2. **#1** (extract CSS/JS) — will show up as *pure movement* in the golden
   diff if you inline correctly. Should be a zero-byte diff.
3. **#2** (Jinja2) — biggest payoff but riskiest; the test is your guardrail
4. Then the rest

### Known quirks / gotchas

- `scripts/fetch.py` has the `{{ }}` f-string escaping problem we hit multiple
  times in the previous session. The no-unescaped-braces test in
  `test_structure.py` guards against regressions here.
- The real `public/index.html` on disk was generated with the *non-deterministic*
  code. Once `fetch.py` runs for real and PRIM data changes, the daily-update
  PR will show reordering churn alongside the real diff. That's a one-time
  cost, not a bug.
- The golden fixture is pinned to `2026-04-10T12:00:00+02:00`. Anything in
  `fetch.py` that branches on "is this event in the past?" relative to *now*
  will behave as though it's April 10 2026. Keep that in mind when writing
  new code.
