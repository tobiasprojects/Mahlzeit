"""Rolands Kantine: HTML link discovery + 2-column page parser.

The restaurant publishes one multi-page PDF per menu period (1 week per page)
from `https://rolandsmaultaschen.de/Im-Rolands/`. Each PDF page is split into
two columns: **Menü 1** (left) and **Menü 2 Vegetarisch** (right).

Layout notes (observed in `testdata/roland_sample.txt`, verified 2026-08-08):
- `pdftotext -layout` output columns are stable: left-column text ends at or
  before column ~70, right-column text starts at or after column ~90. The split
  boundary is fixed at column 80 (mid-gap). If the restaurant changes the
  template and the columns move, revisit the boundary; the fallback is
  `pymupdf` for pixel-precise column coordinates (PROJECT.md §5).
- Weekday labels (Montag…Freitag) sit in the left margin *mid-block*: 1–2 dish
  lines can appear *above* the label and belong to the labelled day. Parsing
  therefore works per column with a small state machine: content accumulates
  into a buffer, a weekday label claims the pending buffer, and a trailing
  allergen parenthetical closes the meal.
- Prices come from the per-column headers `Interne Gäste X,XX €` /
  `Externe Gäste X,XX €`. A dish annotated `Sonderessen X,XX €` is marked
  `sonderessen=true` and **overrides both prices** with that single price
  (the restaurant quotes one price for special dishes).
- Trailing `(...)` on the closing line holds the raw allergen codes (e.g.
  `2, 4, 7, 8, a1|2, c, d, k, m`); kept verbatim.
- The footer (`Partyservice`, `Zusatzstoffe und Allergene`) and page headers
  are discarded, so no phone numbers / contact data are stored (§6).
- `fetch()` scrapes the HTML for current PDF links (never hardcoding the
  `_=<hash>` cache-buster), respects `Crawl-delay: 10`, and caches by date
  range in the filename so already-downloaded weeks are skipped.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Match, Optional, Tuple

from ..model import Day, Meal, Week
from .base import Source, run_pdftotext

PAGE_URL = "https://rolandsmaultaschen.de/Im-Rolands/"

# robots.txt: Allow /.cm4all/uproc.php/ (where the PDFs live), Crawl-delay: 10
CRAWL_DELAY = 10

# Stable column split point in `pdftotext -layout` output (see module docstring).
BOUNDARY = 80

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")

# Page header date range, e.g. "Speisenplan ... Vom 03.08. – 07.08.2026".
# The from-date carries an optional year ("29.12.2025 – 02.01.2026"); its
# trailing dot is consumed separately so `\s*[-–]` still matches.
_DATE_RE = re.compile(
    r"Vom\s+"
    r"(?P<from>\d{2}\.\d{2}(?:\.\d{4})?)\.?\s*[-–]\s*"
    r"(?P<to>\d{2}\.\d{2}\.\d{4})"
)

# Date range inside PDF filenames, e.g. "Speisenplan ... 27.07-31.07.2026.pdf"
_LINK_DATE_RE = re.compile(
    r"(?P<from>\d{2}\.\d{2})\.?(?:\.\d{4})?\s*[-–]\s*"
    r"(?P<to>\d{2}\.\d{2})\.(?P<year>\d{4})"
)

_PRICE_RE = re.compile(r"(\d{1,3},\d{2})\s*€")

_INTERNE_RE = re.compile(r"Interne(?:\s+Gäste)?\s+" + _PRICE_RE.pattern)
_EXTERNE_RE = re.compile(r"Externe(?:\s+Gäste)?\s+" + _PRICE_RE.pattern)
_SONDER_RE = re.compile(r"Sonderessen\s+" + _PRICE_RE.pattern)

# A trailing parenthetical of allergen codes closes a meal.
_ALLERGEN_RE = re.compile(r"\((?P<a>[a-zA-Z0-9|,.\s]+)\)\s*$")

# Short subheadings inside the menu (e.g. "Der Klassiker:") are not dishes.
_SUBHEADING_RE = re.compile(r"^[^,()]{1,60}:\s*$")

_FOOTER_RE = re.compile(r"Partyservice|Zusatzstoffe und Allergene")


def _price(match: Match[str]) -> float:
    return float(match.group(1).replace(",", "."))


class RolandSource(Source):
    """Rolands Kantine weekly speisenplan (HTML-scraped PDFs, 2 columns)."""

    id = "roland"
    name = "Rolands Kantine"
    source_url = PAGE_URL

    # -- fetch -------------------------------------------------------------

    def fetch(self, cache_dir: Path) -> List[Path]:
        target_dir = cache_dir / self.id
        target_dir.mkdir(parents=True, exist_ok=True)
        page_html = self._get(PAGE_URL)
        paths: List[Path] = []
        for url in self._extract_pdf_links(page_html):
            dest = self._cached_copy(target_dir, url)
            if dest is not None:
                paths.append(dest)
                continue
            time.sleep(CRAWL_DELAY)  # robots.txt: Crawl-delay 10
            dest = target_dir / self._filename(url)
            self._download(url, dest)
            paths.append(dest)
        return paths

    def _get(self, url: str) -> str:
        request = urllib.request.Request(
            url, headers={"User-Agent": "mahlzeit/0.1 menu sync bot"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def _download(self, url: str, dest: Path) -> None:
        request = urllib.request.Request(
            urllib.parse.urljoin(PAGE_URL, url),
            headers={"User-Agent": "mahlzeit/0.1 menu sync bot"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError(f"roland: {url} did not return a PDF")
        dest.write_bytes(data)

    def _extract_pdf_links(self, page_html: str) -> List[str]:
        """Unique, html-unescaped, date-sorted speisenplan PDF links from the page.

        Hrefs are kept percent-encoded (`%20` etc.) because `urlopen` rejects
        URLs containing raw spaces; unquoting happens later only when deriving
        the local filename (`_filename`).
        """
        links = set()
        for href in re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', page_html):
            url = html.unescape(href)  # &amp; -> & ; keep %20 encoded for the request
            if "Speisenplan" in url:
                links.add(url)
        return sorted(links, key=lambda url: self._link_date_range(url))

    def _filename(self, url: str) -> str:
        name = url.rsplit("/", 1)[-1]
        name = name.split("?", 1)[0]
        return urllib.parse.unquote(name)

    def _link_date_range(self, url: str) -> Tuple[str, str]:
        """ISO (from, to) for the date range encoded in the PDF filename."""
        match = _LINK_DATE_RE.search(url)
        if match is None:
            raise ValueError(f"roland: cannot parse date range from link {url!r}")
        return self._resolve_link_dates(match)

    def _resolve_link_dates(self, match: Match[str]) -> Tuple[str, str]:
        from_parts = match.group("from").split(".")
        to_parts = match.group("to").split(".")
        year = int(match.group("year"))
        from_year = int(from_parts[2]) if len(from_parts) > 2 else year
        return (
            f"{from_year:04d}-{from_parts[1]}-{from_parts[0]}",
            f"{year:04d}-{to_parts[1]}-{to_parts[0]}",
        )

    def _cached_copy(self, target_dir: Path, url: str) -> Optional[Path]:
        """Path to an existing cached PDF for the same week, if any."""
        from_iso, to_iso = self._link_date_range(url)
        for existing in target_dir.glob("*.pdf"):
            match = _LINK_DATE_RE.search(existing.name)
            if match is None:
                continue
            cached_from, cached_to = self._resolve_link_dates(match)
            if (from_iso, to_iso) == (cached_from, cached_to):
                return existing
        return None

    # -- parse -------------------------------------------------------------

    def parse(self, pdf_paths: List[Path]) -> List[Week]:
        weeks: List[Week] = []
        for pdf_path in pdf_paths:
            text = run_pdftotext(pdf_path)
            for page in text.split("\f"):
                if not page.strip():
                    continue
                weeks.append(self.parse_page(page))
        return weeks

    def parse_page(self, page: str) -> Week:
        from_date, to_date = self._extract_dates(page)
        prices: Dict[str, Tuple[Optional[float], Optional[float]]] = {
            "left": (None, None),
            "right": (None, None),
        }
        columns = {
            "left": self._new_column(type_name="Menü 1", vegan=False),
            "right": self._new_column(type_name="Menü 2", vegan=True),
        }
        in_body = False

        for raw_line in page.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if _FOOTER_RE.search(stripped):
                break
            if "Externe Gäste" in stripped:
                in_body = True
                self._capture_prices(line, prices, _EXTERNE_RE)
                continue
            if "Interne Gäste" in stripped:
                self._capture_prices(line, prices, _INTERNE_RE)
                continue
            if not in_body:
                continue
            weekday = next(
                (
                    name
                    for name in WEEKDAYS
                    if stripped == name or stripped.startswith(name + " ")
                ),
                None,
            )
            left, right = line[:BOUNDARY].strip(), line[BOUNDARY:].strip()
            if weekday is not None:
                for side in ("left", "right"):
                    column = columns[side]
                    if column["day"] is not None and column["buffer"]:
                        self._finalize_meal(column, prices[side])
                    column["day"] = weekday
                self._feed(columns["left"], left[len(weekday):].strip(), prices["left"])
                self._feed(columns["right"], right, prices["right"])
            else:
                self._feed(columns["left"], left, prices["left"])
                self._feed(columns["right"], right, prices["right"])

        days = self._build_days(columns, from_date)
        return Week(
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            days=days,
        )

    def _new_column(self, type_name: str, vegan: bool) -> dict:
        return {
            "type": type_name,
            "vegan": vegan,
            "buffer": [],
            "day": None,
            "sonder": None,
            "meals": {},
        }

    def _capture_prices(self, line: str, prices: Dict, price_re: re.Pattern) -> None:
        for side, half in (("left", line[:BOUNDARY]), ("right", line[BOUNDARY:])):
            match = price_re.search(half)
            if match is None:
                continue
            value = _price(match)
            internal, external = prices[side]
            prices[side] = (value, external) if price_re is _INTERNE_RE else (internal, value)

    def _feed(self, column: dict, line: str, prices: Tuple[Optional[float], Optional[float]]) -> None:
        if not line:
            return
        match = _SONDER_RE.search(line)
        if match is not None:
            column["sonder"] = _price(match)
            line = line[: match.start()].rstrip()
        if not line.strip():
            return
        if _SUBHEADING_RE.match(line):
            return
        if _ALLERGEN_RE.search(line):
            column["buffer"].append(line)
            self._finalize_meal(column, prices)
        else:
            column["buffer"].append(line)

    def _finalize_meal(self, column: dict, prices: Tuple[Optional[float], Optional[float]]) -> None:
        if column["day"] is None:
            raise ValueError(
                "roland: meal closed by an allergen line before any weekday label "
                f"({column['buffer']!r})"
            )
        name = re.sub(r"\s+", " ", " ".join(column["buffer"])).strip()
        name = name.replace("- ", "-")  # rejoin hyphenated words split across lines
        allergens: Optional[str] = None
        match = _ALLERGEN_RE.search(name)
        if match is not None:
            allergens = match.group("a").strip()
            name = name[: match.start()].rstrip()
        if column["sonder"] is not None:
            internal = external = column["sonder"]
        else:
            internal, external = prices
        column["meals"].setdefault(column["day"], []).append(
            Meal(
                type=column["type"],
                name=name,
                vegan=column["vegan"],
                price_internal=internal,
                price_external=external,
                allergens=allergens,
                sonderessen=column["sonder"] is not None,
            )
        )
        column["buffer"] = []
        column["day"] = None
        column["sonder"] = None

    def _build_days(self, columns: dict, start: dt.date):
        left, right = columns["left"], columns["right"]
        for column in (left, right):
            if column["day"] is not None and column["buffer"]:
                self._finalize_meal(column, (None, None))
            if set(column["meals"]) != set(WEEKDAYS):
                raise ValueError(
                    "roland: expected one meal per weekday in each column, got "
                    f"{sorted(column['meals'])} for {column['type']}"
                )
        days = []
        for index, weekday in enumerate(WEEKDAYS):
            meals = left["meals"][weekday] + right["meals"][weekday]
            if not meals:
                raise ValueError(f"roland: no meals parsed for {weekday}")
            days.append(
                Day(
                    date=(start + dt.timedelta(days=index)).isoformat(),
                    weekday=weekday,
                    meals=meals,
                )
            )
        return days

    def _extract_dates(self, page: str) -> Tuple[dt.date, dt.date]:
        match = _DATE_RE.search(page)
        if match is None:
            raise ValueError("roland: could not find 'Vom ...' date range on page")
        from_parts = match.group("from").split(".")
        to_parts = match.group("to").split(".")
        from_year = int(from_parts[2]) if len(from_parts) > 2 else int(to_parts[2])
        return (
            dt.date(from_year, int(from_parts[1]), int(from_parts[0])),
            dt.date(int(to_parts[2]), int(to_parts[1]), int(to_parts[0])),
        )
