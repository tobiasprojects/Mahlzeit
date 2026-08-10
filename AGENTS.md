# AGENTS.md

## Commands

```sh
pytest                      # full suite (68 tests, no network needed)
pip install -e .[dev]       # install CLI (mahlzeit) + pytest
mahlzeit refresh            # download+parse all sources -> data/menus.json
mahlzeit refresh --source roland   # single source
mahlzeit serve              # static server: web/ + data/ on 127.0.0.1:8000
```

`pyproject.toml` sets `pythonpath = ["src"]` for pytest, so tests import the
package without install — but the `mahlzeit` CLI needs `pip install -e .`.

## Constraints

- **Zero runtime dependencies** (stdlib only). No `requests`, no `bs4`, no
  parser libs — sources shell out to `pdftotext` (poppler-utils, must be on
  PATH). Adding a dependency needs justification.
- **Never commit `data/raw/` or `data/menus.json`** (gitignored). `change-report.md`
  at repo root is generated, also gitignored.
- **Tests must never hit the network.** Fetch tests mock `urllib.request.urlopen`;
  parser tests use `testdata/` fixtures. `refresh` is the only place that touches
  the real sites.

## Architecture

- **Plugin model:** every restaurant is one module in `src/mahlzeit/sources/`
  (`roland.py`, `vaihingen.py`) subclassing `Source` (`base.py`). Plugins are
  **auto-discovered at import time** (`sources/__init__.py` scans modules, keys
  instances by `id`). To add a restaurant: new module + `testdata/<id>_sample.txt`
  fixture + test — never register in `registry.py` or touch shared code.
- **`Source` contract:** `id`/`name`/`source_url` class attrs, `fetch(cache_dir)`
  returns local PDF paths, `parse(pdf_paths)` returns `list[Week]`. One failing
  source is logged and skipped by `cli.refresh`, it never kills the run.
- **Data pipeline:** sources -> unified `Menu` model (`model.py`) -> `data/menus.json`
  (`store.py`, atomic tmp+rename write, model validated before write).

## Quirks

- **Crawl etiquette (Rolands):** the real `fetch()` sleeps 10 s per PDF download
  per robots.txt `Crawl-delay` and caches already-fetched weeks by date range in
  the filename. Keep that; don't remove delays.
- **Serialization:** `Week.from_date`/`to_date` map to JSON keys `from`/`to`
  (`from` is a Python keyword). Dates are ISO-8601 strings; optional `Meal`
  fields (`price_internal`, `price_external`, `allergens`, `sonderessen`) are
  omitted from JSON when absent. Keep that shape — the frontend depends on it.
- **Rolands parser:** `Sonderessen X,XX €` overrides both internal/external
  prices with the single quoted price; allergen parenthetical closes a meal.

## Fixtures (`testdata/`)

Store **extracted text only** (`pdftotext -layout <file> -`), never PDFs. Naming:
`<source_id>_sample.txt`. Refresh a fixture only when the restaurant's PDF layout
changes, and verify the parsed output against the original document first.
