"""Tests for the Vaihingen source parser (IMPLEMENTATION.md Step 4).

Parsing is exercised against the committed fixture
`testdata/vaihingen_sample.txt` (extracted text of the real PDF), plus
hand-crafted inputs for error handling and date-range edge cases. `fetch()` is
tested with a mocked HTTP layer so the suite needs no network.
"""

import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from mahlzeit.sources.vaihingen import SOURCE_URL, WEEKDAYS, VaihingenSource

FIXTURE = Path(__file__).resolve().parent.parent / "testdata" / "vaihingen_sample.txt"

PDF_BYTES = b"%PDF-1.4 fake pdf content for fetch tests"

EXPECTED = [
    (
        "2026-08-03",
        "Montag",
        [
            ("Maultaschen mit Pilzrahmsoße und Salat", False),
            ("Pasta mit Zitronenmelissen Pesto", True),
            ("Lauwarmer Linsen Salat mit Brot", False),
        ],
    ),
    (
        "2026-08-04",
        "Dienstag",
        [
            ("Gelbes Thai Curry mit Huhn/Vegi und Reis", True),
            ("Pasta Carbonara", False),
            ("Seafood Chowder (Fisch Eintopf)", False),
        ],
    ),
    (
        "2026-08-05",
        "Mittwoch",
        [
            ("Schweinegeschnetzeltes mit Spätzle", False),
            ("Pasta mit Linsen Bolognese", True),
            ("Griechischer Bauernsalat", False),
        ],
    ),
    (
        "2026-08-06",
        "Donnerstag",
        [
            ("Hackfleisch Gemüse Pfanne mit Bulgur", False),
            ("Pasta Basilikum Pesto", True),
            ("Italienischer Nudelsalat", False),
        ],
    ),
    (
        "2026-08-07",
        "Freitag",
        [
            ("Lachs mit Zitronensoße, Reis und Gemüse", False),
            ("Pasta mit Spinat-Sesam Pesto", True),
            ("Tom Kha Kai Suppe", False),
        ],
    ),
]


def make_text(date_line="  Wochenkarte vom 03.08 – 07.08.2026",
              days=5, dishes_per_day=3):
    """Craft minimal valid extracted text (date line + weekday blocks)."""
    lines = [date_line, ""]
    for index in range(days):
        lines.append(" " * 10 + WEEKDAYS[index])
        for dish in range(dishes_per_day):
            marker = " (V)" if dish == 1 else ""
            lines.append(f"   Gericht {index + 1}.{dish + 1}{marker}")
    lines.append("   (v) =Vegan oder Vegan möglich")
    return "\n".join(lines)


class _FakeResponse:
    """Minimal `urlopen` context-manager response with a fixed body."""

    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


class FixtureParseTest(unittest.TestCase):
    """The committed fixture parses to the week the real PDF shows."""

    @classmethod
    def setUpClass(cls):
        cls.week = VaihingenSource().parse_text(FIXTURE.read_text(encoding="utf-8"))

    def test_week_dates(self):
        self.assertEqual("2026-08-03", self.week.from_date)
        self.assertEqual("2026-08-07", self.week.to_date)

    def test_five_days_monday_to_friday(self):
        self.assertEqual(5, len(self.week.days))
        self.assertEqual(["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"],
                         [day.weekday for day in self.week.days])

    def test_day_dates_match_week(self):
        self.assertEqual(["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                          "2026-08-07"], [day.date for day in self.week.days])

    def test_three_meals_per_day(self):
        for day in self.week.days:
            self.assertEqual(3, len(day.meals), day.weekday)

    def test_names_and_vegan_flags(self):
        for date, weekday, meals in EXPECTED:
            with self.subTest(day=weekday):
                day = next(d for d in self.week.days if d.date == date)
                self.assertEqual(weekday, day.weekday)
                self.assertEqual(
                    [(meal.name, meal.vegan) for meal in day.meals], meals)

    def test_vegan_marker_is_stripped_from_name(self):
        for day in self.week.days:
            for meal in day.meals:
                self.assertNotRegex(meal.name, r"\([vV]\)\s*$", meal.name)

    def test_non_vegan_parenthetical_is_kept(self):
        chowder = self.week.days[1].meals[2]
        self.assertFalse(chowder.vegan)
        self.assertEqual("Seafood Chowder (Fisch Eintopf)", chowder.name)

    def test_names_are_whitespace_collapsed(self):
        for day in self.week.days:
            for meal in day.meals:
                self.assertEqual(meal.name, " ".join(meal.name.split()))

    def test_meals_are_standard_without_prices_allergens(self):
        for day in self.week.days:
            for meal in day.meals:
                self.assertEqual("Standard", meal.type)
                self.assertIsNone(meal.price_internal)
                self.assertIsNone(meal.price_external)
                self.assertIsNone(meal.allergens)
                self.assertFalse(meal.sonderessen)
                self.assertNotIn("price_internal", meal.to_dict())
                self.assertNotIn("allergens", meal.to_dict())

    def test_week_validates(self):
        self.week.validate()


class DateRangeTest(unittest.TestCase):
    def test_from_date_without_year_inherits_to_year(self):
        week = VaihingenSource().parse_text(make_text())
        self.assertEqual("2026-08-03", week.from_date)
        self.assertEqual("2026-08-07", week.to_date)

    def test_both_dates_with_years_cross_year_boundary(self):
        text = make_text("  Wochenkarte vom 29.12.2025 – 02.01.2026")
        week = VaihingenSource().parse_text(text)
        self.assertEqual("2025-12-29", week.from_date)
        self.assertEqual("2026-01-02", week.to_date)

    def test_missing_date_range_raises(self):
        text = "  Montag\n   A\n   B\n   C\n"
        with self.assertRaisesRegex(ValueError, "Wochenkarte"):
            VaihingenSource().parse_text(text)

    def test_malformed_date_raises(self):
        with self.assertRaises(ValueError):
            VaihingenSource().parse_text(
                make_text("  Wochenkarte vom 32.13 – 45.67.2026"))


class StructureErrorTest(unittest.TestCase):
    def test_no_weekday_blocks_raise(self):
        text = "  Wochenkarte vom 03.08 – 07.08.2026\n   only dishes here\n"
        with self.assertRaisesRegex(ValueError, "no weekday blocks"):
            VaihingenSource().parse_text(text)

    def test_fewer_than_three_dishes_raise(self):
        with self.assertRaisesRegex(ValueError, "expected 3 dishes"):
            VaihingenSource().parse_text(make_text(dishes_per_day=2))

    def test_more_than_three_dishes_raise(self):
        with self.assertRaisesRegex(ValueError, "expected 3 dishes"):
            VaihingenSource().parse_text(make_text(dishes_per_day=4))

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            VaihingenSource().parse_text("")


class ParseWrapperTest(unittest.TestCase):
    def test_parse_runs_pdftotext_and_returns_list_of_weeks(self):
        source = VaihingenSource()
        pdf_path = Path("/tmp/fake-vaihingen.pdf")
        with mock.patch("mahlzeit.sources.vaihingen.run_pdftotext",
                        return_value=FIXTURE.read_text(encoding="utf-8")) as run:
            weeks = source.parse([pdf_path])
        run.assert_called_once_with(pdf_path)
        self.assertEqual(1, len(weeks))
        self.assertEqual("2026-08-03", weeks[0].from_date)
        self.assertEqual(5, len(weeks[0].days))


class FetchTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)

    def test_fetch_downloads_pdf_into_source_subdir(self):
        with mock.patch.object(
            urllib.request, "urlopen", return_value=_FakeResponse(PDF_BYTES)
        ) as urlopen:
            paths = VaihingenSource().fetch(self.cache_dir)

        request = urlopen.call_args.args[0]
        self.assertEqual(SOURCE_URL, request.full_url)
        self.assertIsNotNone(request.get_header("User-agent"))

        self.assertEqual([self.cache_dir / "vaihingen" / "Wochenkarte.pdf"], paths)
        self.assertEqual(PDF_BYTES, paths[0].read_bytes())

    def test_fetch_overwrites_existing_copy(self):
        dest = self.cache_dir / "vaihingen" / "Wochenkarte.pdf"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"%PDF-1.4 stale copy")
        with mock.patch.object(
            urllib.request, "urlopen", return_value=_FakeResponse(PDF_BYTES)
        ):
            VaihingenSource().fetch(self.cache_dir)
        self.assertEqual(PDF_BYTES, dest.read_bytes())

    def test_fetch_rejects_non_pdf_response(self):
        with mock.patch.object(
            urllib.request, "urlopen", return_value=_FakeResponse(b"<html>not a pdf")
        ):
            with self.assertRaisesRegex(RuntimeError, "did not return a PDF"):
                VaihingenSource().fetch(self.cache_dir)
        self.assertFalse(
            (self.cache_dir / "vaihingen" / "Wochenkarte.pdf").exists())


if __name__ == "__main__":
    unittest.main()
