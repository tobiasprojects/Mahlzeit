# Implementation Plan — Mahlzeit

Step-by-step plan to implement the project described in `PROJECT.md`. Work through
the steps in order. Each step ends with a **Definition of Done (DoD)** — do not move
on until it passes.

Conventions:
- Reference docs live in `PROJECT.md` (§ numbers cited below).
- Parser design: zero third-party Python deps; shell out to `pdftotext -layout <file> -`.
- Keep sample PDFs/text under `testdata/` for regression tests (never commit PDFs to
  `data/raw/`; do commit small extracted-text fixtures).
- `data/raw/` is gitignored; `data/menus.json` is generated output.
- The sample PDFs referenced in PROJECT.md §5 are gone — re-download them via the URLs
  in §3 when needed (check robots.txt first, respect `Crawl-delay: 10` for Roland).

---

## Step 1 — Scaffold the repo

Create the package skeleton and ignore rules. No logic yet.

Files to create:
- `pyproject.toml` — project metadata, `[project.scripts]` optional; Python 3.14,
  zero runtime deps.
- `src/mahlzeit/__init__.py` — package marker + `__version__`.
- `src/mahlzeit/cli.py`, `model.py`, `store.py`, `registry.py` — empty stubs (imports
  only) so the package imports cleanly.
- `src/mahlzeit/sources/__init__.py`, `sources/base.py`, `sources/vaihingen.py`,
  `sources/roland.py` — empty stubs.
- `data/` + `data/raw/` directories.
- `web/index.html`, `web/app.js`, `web/style.css` — minimal placeholders.
- `.gitignore` — ignore `data/raw/`, `__pycache__/`, `*.egg-info/`, `.venv/`.
- `testdata/` directory + README explaining fixture conventions.

Verify:
- `python3 -m mahlzeit` imports without error (run from repo root with
  `PYTHONPATH=src`, or `pip install -e .`).

**DoD:** `PYTHONPATH=src python3 -c "import mahlzeit"` succeeds; `git status` shows a
clean scaffold with only intended files.

---

## Step 2 — Unified model (`model.py`) + validation

Schema only; no I/O. Matches PROJECT.md §4.

- Dataclasses: `Meal`, `Day`, `Week`, `Restaurant`, plus a `Menu`/root container
  (holds `generated_at` + `restaurants`).
- `Meal` fields (Roland): `type` (Menü 1/Menü 2), `name`, `price_internal?`,
  `price_external?`, `allergens?`, `vegan`, `sonderessen`. Vaihingen meals: `type`
  (Standard), `name`, `vegan` — price/allergen fields optional/absent (None).
- `Day`: `date` (ISO `YYYY-MM-DD`), `weekday`, `meals`.
- `Week`: `from`, `to` (ISO dates).
- `Restaurant`: `id`, `name`, `source_url`, `weeks`.
- `to_dict()` / `from_dict()` for every class.
- `validate_*()` functions raising `ValueError` on: missing ids, malformed ISO dates,
  empty meals, duplicate restaurant ids. Include a small self-check: serialize the
  PROJECT.md §4 example JSON round-trip.

**DoD:** A round-trip test (dict → object → dict) matches exactly; invalid dates and
empty meals are rejected.

---

## Step 3 — `sources/base.py` + `sources/__init__.py` + `registry.py`

The plugin contract (PROJECT.md §2.1). No concrete sources yet.

- `base.py`:
  - `Source` ABC with:
    - `id: str`, `name: str`, `source_url: str` (class attrs).
    - `fetch(cache_dir: Path) -> list[Path]` — download raw PDFs into `cache_dir`
      (`data/raw/<id>/`), own URL discovery + cache-buster handling; returns local
      file paths.
    - `parse(pdf_paths: list[Path]) -> list[Week]` — run `pdftotext -layout <f> -`
      (subprocess), convert text → unified `model.py` schema.
  - Shared subprocess helper `run_pdftotext(path) -> str` (raises on non-zero exit).
- `sources/__init__.py`: auto-discovery — import all modules in the `sources`
  package and expose a `SOURCES` dict keyed by source `id` (so new restaurants are
  one file, no registry edits — §2.1).
- `registry.py`: `get_source(source_id)`, `all_sources()`; returns `SOURCES` entries.

Verify: an ad-hoc dummy source (temporary `testdata/` script, not committed) registers
and is listed by `all_sources()`.

**DoD:** `registry.all_sources()` returns the discovered instances; a temp source with a
fake `parse()` outputting one `Week` runs end-to-end without touching shared code.

---

## Step 4 — Source: Vaihingen (`sources/vaihingen.py`)

Fixed URL + weekday-block parser (PROJECT.md §3.1).

- Re-download `https://naherholungsgebiet-vaihingen.de/mittagskarte/Wochenkarte.pdf`
  (robots.txt: none, 404). Save to `/tmp/opencode/` for development and extract text
  with `pdftotext -layout` → save as `testdata/vaihingen_sample.txt`.
- `fetch()`: download the one PDF to `data/raw/vaihingen/`.
- `parse()`:
  1. Extract date range via regex on `Wochenkarte vom DD.MM. – DD.MM.YYYY` (or similar;
     confirm exact format from real text). Week `from`/`to` → ISO dates.
  2. Split into weekday blocks (Montag…Freitag).
  3. Each weekday → 3 dish lines → 3 `Meal`s; strip `(V)` / `(v)` marker → `vegan=true`;
     type `Standard`; no prices/allergens.
  4. Handle blank lines/whitespace; discard footer/header lines (legend, address).

Verify against `testdata/vaihingen_sample.txt`: 5 days × 3 meals, correct vegan flags,
correct `from`/`to` dates.

**DoD:** `parse()` on the saved fixture yields a `Week` matching the real PDF (check
against the original document). Layout change → only this file + fixture updated.

---

## Step 5 — Source: Roland (`sources/roland.py`)

HTML link discovery + 2-column page parser (PROJECT.md §3.2). The hard one.

- Re-download the HTML from `https://rolandsmaultaschen.de/Im-Rolands/` (robots.txt
  allows PDF path; respect `Crawl-delay: 10`). Extract PDF links matching
  `Speisenplan ... DD.MM.-DD.MM.YYYY.pdf` → save 1–2 PDFs to `/tmp/opencode/` and their
  extracted text as `testdata/roland_sample.txt` (one page per week).
- `fetch()`: GET the page HTML → regex/parse link hrefs → decode `%20` etc. → download
  each PDF into `data/raw/roland/`. Never hardcode the `_=<hash>` cache-buster
  (changes every update). Cache by date-range in filename; skip files already present.
- `parse()`:
  1. For each PDF: for each page, split text into left/right column at a fixed
     boundary column (find the stable break point empirically from the fixture —
     `pdftotext -layout` keeps columns; verify with real output).
  2. Week date range from header `Vom DD.MM. – DD.MM.YYYY`.
  3. Anchor days by weekday names (Montag–Freitag) per column; dishes may span
     multiple lines — merge continuation lines until the next weekday label, price
     line, or `Sonderessen` line.
  4. Extract prices `Interne X,XX € / Externe X,XX €`; `Sonderessen X,XX €` →
     `sonderessen=true` (decide override semantics; document).
  5. Trailing `(...)` → `allergens` string (keep raw, e.g. `2, 4, 7, 8, a1|2, c, d, k, m`).
  6. `Menü 2` column → `vegan=true`; `Menü 1` → `vegan=false`.

Verify against `testdata/roland_sample.txt` per week: 2 menus × 5 days, prices,
allergens, dates match the source PDF.

**DoD:** `parse()` on the fixture yields weeks that match the real document; if column
splitting is unreliable, record the observed boundary and the fallback plan (add
`pymupdf` optionally — §5).

---

## Step 6 — `store.py` + CLI (`cli.py`)

Wire it together (PROJECT.md §8.4).

- `store.py`:
  - `read_menus(path) -> Menu` (tolerant: return empty if missing).
  - `write_menus(path, menu)` — pretty-printed JSON, `generated_at` set to now with
    local tz offset (`2026-08-07T22:00:00+02:00` format), atomic write (tmp + rename).
  - Optional `append_history` / `keep_weeks` policy (pending decision §9 — start with
    "current + next week only").
- `cli.py`:
  - `refresh` — for each source in registry: `fetch()` → `parse()` → merge into one
    `Menu` → `write_menus("data/menus.json")`. Each source isolated (wrap per-source
    try/except, log and continue, so one failure doesn't kill the run).
  - `serve` — `python -m http.server` serving `web/` with `data/` reachable
    (symlink `web/data -> ../data` or custom handler serving both roots; pick simplest
    and document).
  - `--source` filter flag for running one source.

Verify: run `refresh` end-to-end with real network; `data/menus.json` matches the §4
schema and opens cleanly.

**DoD:** `PYTHONPATH=src python3 -m mahlzeit refresh` writes a valid `menus.json`;
`serve` + browser shows the JSON. A fake source that raises is logged and skipped.

---

## Step 7 — Web dashboard (`web/`)

Vanilla JS static dashboard, data-driven by `restaurants[]` (PROJECT.md §7).

- `index.html` — layout, source attribution + link ("zum Original"), freshness
  (`generated_at`), stale-data warning.
- `app.js`:
  - Fetch `data/menus.json` (same-origin via the `serve` handler).
  - Side-by-side restaurant columns; day rows with week/day navigation.
  - "Today" highlight; expired weeks visually marked (computed client-side from ISO
    dates — §4).
  - Vegetarian/vegan filter (Roland: `type == "Menü 2"`; Vaihingen: `meal.vegan`).
  - Show prices (internal/external) + allergen codes when present; `Sonderessen`
    badge.
  - Render gracefully when a field is absent (e.g. Vaihingen has no prices).
- `style.css` — clean, readable, mobile-friendly.

Verify: load `serve`, check both restaurants, today highlight, filters, stale warning.
Test with a `menus.json` containing only Vaihingen (data-driven frontend — §2.1).

**DoD:** All §7 features work against real `menus.json`; frontend renders any number of
restaurants from the data alone.

---

## Step 8 — Regression tests + sample fixtures

Lock down parser behavior (the fragile part, §2).

- `tests/` with `pytest` (dev-only dependency) or `unittest` (zero-dep; prefer
  `unittest` to keep runtime deps at zero).
- Fixtures: commit the extracted-text files from Steps 4/5 under `testdata/`; a README
  explains how to regenerate them (`pdftotext -layout`) and how to re-download the PDFs
  politely.
- Tests:
  - `model_test.py` — round-trip, validation failures.
  - `vaihingen_test.py` — fixture → expected 5×3 meals, vegan flags, dates.
  - `roland_test.py` — fixture → expected menus, prices, allergens, dates.
  - `store_test.py` — write/read round-trip, atomicity, missing-file tolerance.
  - `registry_test.py` — discovery, isolation on failure.
- Add a `testdata/README` noting when fixtures must be refreshed (restaurant changed
  layout) and the refresh procedure.

Verify: `python3 -m unittest discover -s tests` (or `pytest`) is green.

**DoD:** Full test suite passes; each parser has at least one fixture-backed regression
test.

---

## Step 9 — Scheduling + deployment

Pending decisions in §9: cron vs CI, LAN vs anywhere. Default to LAN + local cron.

- Local: `cron` entry `0 6 * * 1-5` (weekdays, pending §9 decision) running
  `refresh` into the repo's `data/`. Document in README.
- Anywhere-access option (defer until decided): GitHub Actions nightly `refresh` →
  commit `menus.json` → host `web/` on GitHub Pages/Netlify (free, always-on). Add
  `.github/workflows/refresh.yml` when this is chosen.

**DoD:** A `refresh` runs unattended and writes current data; README documents the
schedule and how to change it.

---

## Step 10 — Polish + README

- Filters refined; freshness warning styled; today highlight edge cases (weekend:
  no menu today → highlight nearest upcoming or none).
- `README.md` rewritten per §8.7: what it is, install (`pip install -e .`), usage
  (`refresh`, `serve`), architecture overview, how to add a restaurant (§2.1),
  legal notes (§6: facts only, attribution, no personal data), scheduling.
- Final pass: run `refresh` + `serve`, full test suite, review `menus.json` and the
  rendered page against the §4 schema and §7 features.

**DoD:** README complete and accurate; end-to-end run works from a fresh clone;
`PROJECT.md`'s open questions (§9) resolved or explicitly marked as deferred.

---

## Open decisions to make along the way (§9)

1. Cron schedule — daily vs weekdays only (Step 9; default weekdays `0 6 * * 1-5`).
2. LAN-only vs anywhere-access — controls whether Step 9 goes local or CI+static host.
3. History archive — keep past weeks or current+next only (Step 6; default current+next,
   archive is a later enhancement).
