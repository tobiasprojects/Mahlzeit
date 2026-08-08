# Mahlzeit — Project Handoff / Plan

A personal dashboard that shows the weekly menus of two Stuttgart-Vaihingen restaurants.
This file is the single source of truth for the project. If a session is lost, start here.

**Status:** Planning complete, architecture decided. No code written yet.

---

## 1. Goal

Easily view the meals that are **currently available** and **upcoming** at two restaurants:

1. **Naherholungsgebiet** (Vaihingen) — publishes a weekly lunch menu
2. **Rolands Kantine** (Rolands Maultaschen) — publishes a weekly speisenplan

Both restaurants publish their menus **only as PDFs**, so the project must download, parse,
and render them as a readable dashboard. Accessible from multiple devices.

---

## 2. Architecture

Lightweight Python pipeline + dependency-free static dashboard. No backend required at view time.
Each restaurant is a self-contained **source plugin**, so adding a new restaurant never touches
shared code.

```
Mahlzeit/
├── pyproject.toml            # packaging for src/mahlzeit
├── src/mahlzeit/
│   ├── __init__.py
│   ├── cli.py                # CLI: `refresh` and `serve`
│   ├── model.py              # unified schema + validation
│   ├── store.py              # read/write data/menus.json (+ metadata)
│   ├── registry.py           # source registry: source id -> plugin instance
│   └── sources/              # one module per restaurant (plugin style)
│       ├── __init__.py       # auto-discovers and exposes all sources
│       ├── base.py           # Source interface (fetch + parse contract)
│       ├── vaihingen.py      # Naherholungsgebiet: fixed URL + weekday-block parser
│       └── roland.py         # Rolands Kantine: HTML link discovery + 2-column parser
├── data/
│   └── menus.json            # generated output, served statically
├── web/
│   ├── index.html            # single-file dashboard, vanilla JS
│   ├── app.js                # renders weeks/days, filters, "today" highlight
│   └── style.css
└── README.md                 # end-user run instructions (write later)
```

**Data flow:**

```
cron (daily ~06:00) or manual `refresh`
   → registry: for each source plugin → fetch (download PDFs, cache in data/)
   → registry: for each source plugin → parse (pdftotext → unified model)
   → write data/menus.json
   → browser loads JSON via static file server
```

**Key properties:**

- Zero frameworks on the serving side; view time is just static files + JSON.
- The parser is the only hard/fragile part (PDF layouts change). Keep each parser inside its
  own source module with sample PDFs / expected outputs for regression testing, so a layout
  change only ever affects one restaurant.
- A backend (Option B) can be added later without redoing the parsers.

### 2.1 Adding a new restaurant (extension contract)

New restaurants are added without modifying existing parsers or any shared code:

1. Create `src/mahlzeit/sources/<id>.py` implementing the `Source` interface from
   `sources/base.py`: a stable `id`/`name`, a `fetch()` that downloads the raw PDFs
   (handles its own URL discovery, cache-busters, robots.txt / crawl-delay), and a `parse()`
   that converts the extracted PDF text into the unified `model.py` schema.
2. Register the module in `sources/__init__.py` (or rely on auto-discovery by id).
3. Done: `registry.py` wires it up, `cli.py refresh` runs every registered source, and `web/`
   renders whatever restaurants are present in `menus.json` — the frontend is data-driven by
   `restaurants[]` and needs no changes for a new restaurant.

Shared infrastructure stays generic: `model.py` (schema), `store.py` (JSON I/O),
`registry.py` (plugin wiring) and the frontend all work for any number of restaurants.
Restaurant-specific knowledge (URLs, PDF layouts, marker legends, prices) lives only inside
its own source module.

---

## 3. Data sources — findings (verified 2026-08-07)

### 3.1 Vaihingen (naherholungsgebiet-vaihingen.de)

| Item | Value |
|---|---|
| Menu URL | `https://naherholungsgebiet-vaihingen.de/mittagskarte/Wochenkarte.pdf` |
| Type | Single-page PDF, text-based (extractable with `pdftotext -layout`) |
| URL stability | Fixed URL; the file is overwritten each week (no date in the filename) |
| Scope | One week, Monday–Friday, **3 dishes per day** |
| Vegan marker | `(V)` = "Vegan oder Vegan möglich" (legend at bottom) |
| robots.txt | None (404) |

**Structure of extracted text:**

```
             Ihr Mittagsmenü aus Stuttgart-Vaihingen
  Wochenkarte vom 03.08 – 07.08.2026
                             Montag
     Maultaschen mit Pilzrahmsoße und Salat
        Pasta mit Zitronenmelissen Pesto (V)
          Lauwarmer Linsen Salat mit Brot
                            Dienstag
  ...
   (v) =Vegan oder Vegan möglich
   Naherholungsgebiet | Industriestraße 5, 70565 Stuttgart
```

Parsing: extract date range from `Wochenkarte vom DD.MM – DD.MM.YYYY`, then split into
weekday blocks; each weekday is followed by 3 dish lines; strip `(V)`.

### 3.2 Rolands Kantine (rolandsmaultaschen.de)

| Item | Value |
|---|---|
| Page URL | `https://rolandsmaultaschen.de/Im-Rolands/` |
| Type | HTML page with **2 PDF download links** (current week + next 1–2 weeks) |
| PDF path pattern | `/.cm4all/uproc.php/0/Speisenplan%20BGHM%20Kantine%20DD.MM.-DD.MM.YYYY.pdf?cdp=a&_=<hash>` |
| Cache-buster | `_=<hash>` changes whenever the file is updated → **must scrape the HTML each refresh** to find current links (do NOT hardcode) |
| PDF content | Multi-page, **1 week per page**; header `Vom DD.MM. – DD.MM.YYYY` |
| Layout | 2-column: **Menü 1** (left), **Menü 2 Vegetarisch** (right) |
| Prices | Interne Gäste 6,00 € / Externe Gäste 8,00 €; some dishes marked `Sonderessen X,XX €` |
| Allergens | Trailing codes like `(a1\|2, c, d, k, m)`; legend at page bottom |
| robots.txt | **Allows** `/.cm4all/uproc.php/` (where the PDFs live); sets `Crawl-delay: 10` |

**Example links found (2026-08-07 — will be stale soon):**

- Current: `https://rolandsmaultaschen.de/.cm4all/uproc.php/0/Speisenplan%20BGHM%20Kantine%2003.08.-14.08.2026.pdf?cdp=a&_=19f9efe2c10`
- Past: `https://rolandsmaultaschen.de/.cm4all/uproc.php/0/Speisenplan%20BGHM%20Kantine%2027.07-31.07.2026.pdf?cdp=a&_=19f7b7804f8`

**Structure of extracted text (per week):**

```
Speisenplan                                          Vom 03.08. – 07.08.2026
Öffnungszeiten: 8:00 – 14:00 Uhr                     Mittag 11:30 – 13:30 Uhr
    ... Menü 1 ...                                   ... Menü 2 Vegetarisch ...
    ... Interne 6,00 € / Externe 8,00 € ...          ... same prices ...
    Montag   Hackbällchen Ragout mit Paprika, ...    Frühlingsrolle dazu Gemüsereis und
                 Tomatensauce und Kichererbsen                  Sojasauce (a1|2, c, d, k, m)
                 (2, 4, 7, 8, a1|2, c, d, k, m)
```

Parsing: split each page into left/right columns (fixed boundary in `pdftotext -layout`
output); weekday labels anchor days; dishes may span multiple lines; trailing `(...)` = allergens;
`Sonderessen` overrides the price; date range from the `Vom ...` line.

---

## 4. Unified data model (data/menus.json)

```json
{
  "generated_at": "2026-08-07T22:00:00+02:00",
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
                  "name": "Hackbällchen Ragout mit Paprika, Zucchini, Tomatensauce und Kichererbsen",
                  "price_internal": 6.0,
                  "price_external": 8.0,
                  "allergens": "2, 4, 7, 8, a1|2, c, d, k, m",
                  "vegan": false,
                  "sonderessen": false
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "vaihingen",
      "name": "Naherholungsgebiet",
      "source_url": "https://naherholungsgebiet-vaihingen.de/mittagskarte/Wochenkarte.pdf",
      "weeks": [
        {
          "from": "2026-08-03",
          "to": "2026-08-07",
          "days": [
            {
              "date": "2026-08-03",
              "weekday": "Montag",
              "meals": [
                { "type": "Standard", "name": "Maultaschen mit Pilzrahmsoße und Salat", "vegan": false },
                { "type": "Standard", "name": "Pasta mit Zitronenmelissen Pesto", "vegan": true }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Notes:
- Every restaurant/week/day includes `from`/`to`/`date` so the frontend can compute
  "today / upcoming / expired" purely client-side from the ISO dates.
- Vaihingen has no prices/allergens; keep those fields optional/absent.
- Keep the raw PDFs cached in `data/` (or a gitignored `data/raw/`) for re-parsing, but never commit them.

---

## 5. Environment / tooling

Verified available on this machine (Linux):

- `pdftotext` (from poppler-utils) — use `pdftotext -layout <file> -` for fixed-width output
- `pdftoppm`, `pdfimages`
- `python3` (via pyenv shims) — no third-party PDF libs confirmed (pymupdf/pdfplumber imports failed)

Design the parser around `pdftotext` subprocess (zero Python deps). `pymupdf` (`import fitz`)
can be added later if column extraction becomes unreliable.

Sample PDFs (temp, may be deleted): `/tmp/opencode/vaihingen_wochenkarte.pdf`,
`/tmp/opencode/roland_speisenplan.pdf`. If lost, re-download via the URLs in §3.

---

## 6. Legal / politeness guardrails (verified & decided)

- **Copyright (UrhG):** dish names/prices are short factual data, generally below the
  threshold of originality. **Only extract facts** — never mirror the PDFs or copy longer
  text blocks / allergen tables verbatim.
- **robots.txt:** Roland explicitly allows `/.cm4all/uproc.php/`; **respect `Crawl-delay: 10`**
  → at most one daily refresh per source, minimal requests (1 HTML + 2 PDFs for Roland, 1 PDF for Vaihingen).
- **Cache locally**, never hotlink/embed the restaurants' files.
- **No personal data** (don't scrape/store the phone/email that appear in the PDFs).
- **UI attribution:** show source name + link ("zum Original") and the fetch timestamp
  (`generated_at`) with a stale-data warning.

---

## 7. Dashboard features (agreed)

- Side-by-side view of both restaurants.
- Today highlighted; week/day navigation; next week shown.
- Vegetarian/vegan filter (Roland: Menü 2; Vaihingen: `(V)` tag).
- Prices (Roland internal/external) and allergen codes displayed.
- Expired weeks visually marked; freshness indicator ("zuletzt aktualisiert: ...").
- Optional later: free-text search, history archive.

---

## 8. Roadmap / next steps (in order)

1. **Scaffold** the repo: `pyproject.toml`, `src/mahlzeit/` package skeleton, `.gitignore`
   (ignore `data/raw/`).
2. **sources/base.py + registry.py** — define the `Source` interface and the plugin
   registry; `cli.py refresh` iterates the registry so each source's fetch+parse runs in isolation.
3. **sources/vaihingen.py + sources/roland.py** — implement fetch+parse per restaurant
   (Vaihingen: fixed URL + weekday-block parser; Roland: HTML link discovery + 2-column
   page parser, see §3). Save sample extracted text as fixtures for regression tests.
4. **store.py + cli.py** — `python -m mahlzeit refresh` writes `data/menus.json`;
   `python -m mahlzeit serve` starts a static server (`python -m http.server` over `web/` + `data/`).
5. **web/** — static dashboard reading `../data/menus.json`.
6. **Scheduling** — cron `0 6 * * 1-5` (or daily) calling `refresh`. For anywhere-access
   later: GitHub Actions nightly refresh → commit/push `menus.json` → host `web/` on
   Netlify/GitHub Pages (free, always-on).
7. **Polish** — filters, freshness warning, README.

---

## 9. Open questions / decisions still pending

- Exact cron schedule (daily vs weekdays only).
- LAN-only vs anywhere-access (affects step 6: local cron vs GitHub Actions + static host).
- Whether to keep a history archive (past weeks) or only current + next week.
