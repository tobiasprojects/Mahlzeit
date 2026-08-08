"""Naherholungsgebiet (Vaihingen): fixed URL + weekday-block parser.

The restaurant publishes one single-page PDF per week at a fixed URL
(PROJECT.md §3.1): Monday-Friday, 3 dishes per day. A trailing `(V)`/`(v)`
marks a dish as vegan (legend at the page bottom); prices and allergens are
not published. Header and footer lines (title, date range, legend, address)
are discarded.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.request
from pathlib import Path
from typing import List, Match, Optional, Tuple

from ..model import Day, Meal, Week
from .base import Source, run_pdftotext

SOURCE_URL = "https://naherholungsgebiet-vaihingen.de/mittagskarte/Wochenkarte.pdf"

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")

# e.g. "Wochenkarte vom 03.08 – 07.08.2026" (the "from" date usually has no year)
_DATE_RE = re.compile(
    r"Wochenkarte\s+vom\s+"
    r"(?P<from>\d{2}\.\d{2}(?:\.\d{4})?)\s*[-–]\s*"
    r"(?P<to>\d{2}\.\d{2}(?:\.\d{4})?)"
)

# Legend and address footer lines to discard
_FOOTER_RE = re.compile(r"\([vV]\)\s*=|Naherholungsgebiet\s*\|"
                        r"|naherholungsgebiet-vaihingen\.de|Telefon")

# Trailing vegan marker, e.g. "Pasta mit Pesto (V)"
_VEGAN_RE = re.compile(r"\([vV]\)\s*$")


class VaihingenSource(Source):
    """Naherholungsgebiet weekly lunch menu (single fixed PDF)."""

    id = "vaihingen"
    name = "Naherholungsgebiet"
    source_url = SOURCE_URL

    def fetch(self, cache_dir: Path) -> List[Path]:
        """Always re-download: the fixed URL is overwritten with the new week."""
        target_dir = cache_dir / self.id
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / "Wochenkarte.pdf"
        request = urllib.request.Request(
            SOURCE_URL, headers={"User-Agent": "mahlzeit/0.1 menu sync bot"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError(f"{self.id}: {SOURCE_URL} did not return a PDF")
        dest.write_bytes(data)
        return [dest]

    def parse(self, pdf_paths: List[Path]) -> List[Week]:
        return [self.parse_text(run_pdftotext(path)) for path in pdf_paths]

    def parse_text(self, text: str) -> Week:
        """Parse extracted text (`pdftotext -layout`) into one `Week`."""
        from_date, to_date = self._extract_dates(text)
        blocks: List[Tuple[str, List[str]]] = []
        current: Optional[Tuple[str, List[str]]] = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in WEEKDAYS:
                current = (stripped, [])
                blocks.append(current)
            elif current is not None and not _FOOTER_RE.search(stripped):
                current[1].append(stripped)
        if not blocks:
            raise ValueError(
                f"vaihingen: no weekday blocks found in extracted text "
                f"({from_date}..{to_date})"
            )
        return Week(
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            days=self._build_days(blocks, from_date),
        )

    def _extract_dates(self, text: str) -> Tuple[dt.date, dt.date]:
        match = _DATE_RE.search(text)
        if match is None:
            raise ValueError("vaihingen: could not find 'Wochenkarte vom ...' date range")
        return self._resolve_dates(match)

    def _resolve_dates(self, match: Match[str]) -> Tuple[dt.date, dt.date]:
        from_parts = match.group("from").split(".")
        to_parts = match.group("to").split(".")
        from_year = int(from_parts[2]) if len(from_parts) > 2 else None
        to_year = int(to_parts[2]) if len(to_parts) > 2 else None
        if from_year is None and to_year is None:
            raise ValueError("vaihingen: date range has no year")
        from_year = from_year if from_year is not None else to_year
        to_year = to_year if to_year is not None else from_year
        return (
            dt.date(from_year, int(from_parts[1]), int(from_parts[0])),
            dt.date(to_year, int(to_parts[1]), int(to_parts[0])),
        )

    def _build_days(self, blocks: List[Tuple[str, List[str]]], start: dt.date):
        days = []
        for index, (weekday, lines) in enumerate(blocks):
            if len(lines) != 3:
                raise ValueError(
                    f"vaihingen: expected 3 dishes on {weekday}, got {len(lines)}: "
                    f"{lines!r}"
                )
            meals = [self._make_meal(line) for line in lines]
            days.append(
                Day(
                    date=(start + dt.timedelta(days=index)).isoformat(),
                    weekday=weekday,
                    meals=meals,
                )
            )
        return days

    def _make_meal(self, line: str) -> Meal:
        vegan = _VEGAN_RE.search(line) is not None
        name = _VEGAN_RE.sub("", line).strip()
        return Meal(type="Standard", name=re.sub(r"\s+", " ", name), vegan=vegan)
