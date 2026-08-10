# Mahlzeit

A small dashboard for local canteens. Weekly menu plans are synced from the
restaurants' own PDFs into a single static JSON file, which a no-dependency web
frontend renders as a German-language week view.

Supported restaurants:

- **Rolands Kantine** (Stuttgart) — HTML link discovery + 2-column PDF parser,
  with prices, allergens and `Sonderessen` markings.
- **Naherholungsgebiet** (Stuttgart-Vaihingen) — single fixed weekly PDF.

## How it works

```
restaurant PDFs  --fetch/parse-->  data/menus.json  --static site-->  browser
   (sources/)          (model/)       (store/)           (web/)
```

Each restaurant is a **source plugin** (`src/mahlzeit/sources/`). Sources are
auto-discovered at import time, so adding a restaurant is a single new module —
shared code never changes. `pdftotext` (poppler) extracts the text; every source
owns its own layout parsing and URL discovery.

`refresh` runs every source in isolation: one failing source is logged and
skipped, the others still produce a menu. Weeks are pruned to the current and
next week, and `data/menus.json` is written atomically (temp file + rename).

The frontend (`web/`) is plain HTML/CSS/JS with no build step and no
dependencies. It loads `data/menus.json` same-origin, highlights today, and can
filter to vegetarian/vegan dishes. "Today", "upcoming" and "expired" states are
computed client-side from the ISO dates in the data.

## Requirements

- Python 3.10+
- [poppler-utils](https://poppler.freedesktop.org/) (`pdftotext` on PATH)
- No third-party Python packages (standard library only)

## Installation

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Development dependencies (pytest):

```sh
pip install -e .[dev]
```

## Usage

```sh
# Download + parse all sources, write data/menus.json
mahlzeit refresh

# Only one source
mahlzeit refresh --source vaihingen

# Serve web/ + data/ on http://127.0.0.1:8000
mahlzeit serve
```

The commands are also available via `python -m mahlzeit refresh` /
`python -m mahlzeit serve`.

> Running `refresh` downloads PDFs from the restaurants' websites. Respect
> `robots.txt` and crawl-delays; sources do this (e.g. Rolands waits 10 s per
> download and caches already-fetched weeks).

## Data model

`data/menus.json` follows a fixed schema:

```json
{
  "generated_at": "2026-08-08T14:59:01+02:00",
  "restaurants": [
    {
      "id": "roland",
      "name": "Rolands Kantine",
      "source_url": "https://rolandsmaultaschen.de/Im-Rolands/",
      "weeks": [
        {
          "from": "2026-08-03",
          "to": "2026-08-07",
          "days": [
            {
              "date": "2026-08-03",
              "weekday": "Montag",
              "meals": [
                {
                  "type": "Menü 1",
                  "name": "Hackbällchen Ragout mit Paprika",
                  "vegan": false,
                  "price_internal": 6.0,
                  "price_external": 8.0,
                  "allergens": "2, 4, 7, 8, a1|2, c, d, k, m"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Dates/datetimes are ISO-8601 strings. Optional fields (`price_internal`,
`price_external`, `allergens`, `sonderessen`) are omitted when absent. The
schema is validated on read and before write (`src/mahlzeit/model.py`).

## Adding a restaurant

1. Create `src/mahlzeit/sources/<your_id>.py` with a `Source` subclass:
   `id`, `name`, `source_url`, `fetch(cache_dir)` and `parse(pdf_paths)`.
2. Add a parser fixture `testdata/<your_id>_sample.txt` (extracted text from
   `pdftotext -layout <file> -`, never the PDF itself).
3. Add a `tests/test_<your_id>.py`; parsing tests run against the fixture,
   `fetch()` against a mocked HTTP layer, so the suite needs no network.

The registry picks the new source up automatically.

## Testing

```sh
pytest
```

Parser tests run against committed fixtures in `testdata/`; fetch tests mock the
network. No test touches a restaurant website.

## Project layout

```
src/mahlzeit/
  cli.py            # refresh + serve subcommands
  model.py          # Menu/Restaurant/Week/Day/Meal schema + validation
  store.py          # atomic read/write of data/menus.json, week retention
  registry.py       # source registry (id -> plugin)
  sources/
    base.py         # Source interface + pdftotext helper
    roland.py       # Rolands Kantine (HTML-scraped PDFs)
    vaihingen.py    # Naherholungsgebiet (fixed PDF)
web/                # static frontend (no build, no dependencies)
data/               # generated menus.json + raw PDF cache (gitignored)
testdata/           # pdftotext fixtures for parser tests
tests/              # pytest suite
```

## Privacy

`data/raw/` (downloaded PDFs) and `data/menus.json` are gitignored and never
committed. Sources discard headers/footers containing contact data (addresses,
phone numbers) during parsing.
