"""Tests for the Roland source parser (IMPLEMENTATION.md Step 5).

Parsing is exercised against the committed fixture
`testdata/roland_sample.txt` (extracted text of the real PDF: two pages, one
week each), plus hand-crafted inputs for error handling and date-range edge
cases. `fetch()` is tested with a mocked HTTP layer so the suite needs no
network and never hits the site.
"""

import urllib.request
from pathlib import Path
from unittest import mock

import pytest

from mahlzeit.sources.roland import PAGE_URL, RolandSource

FIXTURE = Path(__file__).resolve().parent.parent / "testdata" / "roland_sample.txt"

PDF_BYTES = b"%PDF-1.7 fake pdf content for fetch tests"

# Percent-encoded hrefs as they appear in the HTML; html-unescaped only.
PDF_URL_A = (
    "https://rolandsmaultaschen.de/.cm4all/uproc.php/0/"
    "Speisenplan%20BGHM%20Kantine%2027.07-31.07.2026.pdf?cdp=a&_=19f7b7804f8"
)
PDF_URL_B = (
    "https://rolandsmaultaschen.de/.cm4all/uproc.php/0/"
    "Speisenplan%20BGHM%20Kantine%2003.08.-14.08.2026.pdf?cdp=a&_=19f9efe2c10"
)

# Simple page with two speisenplan links (one uses &amp; one uses &), plus an
# unrelated PDF that must be ignored.
SAMPLE_HTML = (
    "<html><body>"
    '<a href="/.cm4all/uproc.php/0/Speisenplan%20BGHM%20Kantine%20'
    '27.07-31.07.2026.pdf?cdp=a&amp;_=19f7b7804f8">aktuell</a>'
    '<a href="/.cm4all/uproc.php/0/Speisenplan%20BGHM%20Kantine%20'
    '03.08.-14.08.2026.pdf?cdp=a&_=19f9efe2c10">kantine</a>'
    '<a href="/.cm4all/uproc.php/0/not-a-menu.pdf">other</a>'
    "</body></html>"
)

# (weekday, [(type, name, internal, external, vegan, sonderessen, allergens)])
WEEK_1 = "2026-08-03", "2026-08-07"
WEEK_2 = "2026-08-10", "2026-08-14"
WEEK_1_DATES = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
WEEK_2_DATES = ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]
WEEK_1_MEALS = {
    "Montag": [
        ("Menü 1", "Hackbällchen Ragout mit Paprika, Zucchini, Tomatensauce und Kichererbsen",
         6.0, 8.0, False, False, "2, 4, 7, 8, a1|2, c, d, k, m"),
        ("Menü 2", "Frühlingsrolle dazu Gemüsereis und Sojasauce",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Dienstag": [
        ("Menü 1", "Schnitzel gebacken dazu Pommes frites",
         8.5, 8.5, False, True, "a1|2, c, d, k, m"),
        ("Menü 2", "Kokos Curry mit Gemüse und Veggie Hack",
         6.0, 8.0, True, False, "a1|2, c, d, k, l, m"),
    ],
    "Mittwoch": [
        ("Menü 1", "Spaghetti Pfanne mit Beefsteak Hackfleisch, Spinat, Möhren und Feta an leichter Sahnesauce",
         6.0, 8.0, False, False, "a1|2, c, d, k, m"),
        ("Menü 2", "Frisches Pilzomelette mit Champignons, Pfifferlingen und Kartoffeln",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Donnerstag": [
        ("Menü 1", "Gratinierte Hähnchenfilets a la Caprese mit Tomaten, Mozzarella dazu Kräuter-Knoblauch Baguette",
         6.0, 8.0, False, False, "a1|2, c, d, k, m"),
        ("Menü 2", "Lasagne Spinat-Ricotta dazu Salat vom Büfett",
         6.0, 8.0, True, False, "a1|2, c, d, k, l, m"),
    ],
    "Freitag": [
        ("Menü 1", "Gemischter Fischteller mit Lachsfilet, knusprigen Kibbelinge, Sauce Tatar dazu Kartoffelsalat",
         9.5, 9.5, False, True, "a1|2, b, c, d, k, m"),
        ("Menü 2", "Hausgemachter Kaiserschmarrn dazu Apfelkompott",
         6.0, 8.0, True, False, "a1|2, c, k"),
    ],
}
WEEK_2_MEALS = {
    "Montag": [
        ("Menü 1", "Unsere Besten: 2 hausgemachte Maultaschen mit Zwiebelschmelze dazu Kartoffelsalat",
         6.0, 8.0, False, False, "7, a1|2, c, d, k, m"),
        ("Menü 2", "Kartoffel-Rösti mit Blumenkohl und Sauce Hollandaise mit Käse gratiniert",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Dienstag": [
        ("Menü 1", "½ knuspriges Hähnchen aus dem Backofen dazu Pommes frites",
         6.0, 8.0, False, False, "a1|2, c, d, k, m"),
        ("Menü 2", "One Pot Tortellini mit Zucchini, Kirschtomaten, Fetakäse, Thymian an leichter Tomatensauce",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Mittwoch": [
        ("Menü 1", "Krautwickel mit Specksößle dazu Kartoffelstampf",
         6.0, 8.0, False, False, "1,2,3,4, 8, a1|2, c, d, k, m"),
        ("Menü 2", "Veggie Teller nach Laune des Kochs",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Donnerstag": [
        ("Menü 1", "Spanferkel-Rollbraten aus dem Backofen dazu Spätzle und Bratensauce",
         9.0, 9.0, False, True, "a1|2, c, d, k, m"),
        ("Menü 2", "Nudelpfanne mit Champignon und Steinpilz Ragout",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
    "Freitag": [
        ("Menü 1", "Rotbarschfilet gebacken dazu Sauce Remoulade und Kartoffelsalat",
         6.0, 8.0, False, False, "a1|2, b, c, d, k, m"),
        ("Menü 2", "Salatteller vom Büfett mit Back Käse, Preiselbeeren und Baguette",
         6.0, 8.0, True, False, "a1|2, c, d, k, m"),
    ],
}


def _parse_fixture():
    """Split the fixture on form feeds and parse each page into a Week."""
    text = FIXTURE.read_text(encoding="utf-8")
    return [RolandSource().parse_page(page) for page in text.split("\f") if page.strip()]


@pytest.fixture(scope="module")
def weeks():
    """The committed fixture parses to the weeks the real PDF shows."""
    return _parse_fixture()


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


def test_two_weeks_one_per_page(weeks):
    assert 2 == len(weeks)
    assert [WEEK_1[0], WEEK_2[0]] == [w.from_date for w in weeks]
    assert [WEEK_1[1], WEEK_2[1]] == [w.to_date for w in weeks]


def test_five_days_monday_to_friday(weeks):
    for week in weeks:
        assert ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"] == [
            day.weekday for day in week.days
        ]


def test_day_dates_run_monday_to_friday(weeks):
    for week, dates in ((weeks[0], WEEK_1_DATES), (weeks[1], WEEK_2_DATES)):
        assert dates == [day.date for day in week.days]


def test_two_meals_per_day(weeks):
    for week in weeks:
        for day in week.days:
            assert 2 == len(day.meals), f"{week.from_date} {day.weekday}"
            assert {"Menü 1", "Menü 2"} == {m.type for m in day.meals}


def test_expected_meals(weeks):
    for week, expected in ((weeks[0], WEEK_1_MEALS), (weeks[1], WEEK_2_MEALS)):
        for day in week.days:
            actual = [
                (m.type, m.name, m.price_internal, m.price_external,
                 m.vegan, m.sonderessen, m.allergens)
                for m in day.meals
            ]
            assert expected[day.weekday] == actual


def test_menu_2_is_vegan(weeks):
    for week in weeks:
        for day in week.days:
            vegan = {m.type: m.vegan for m in day.meals}
            assert not vegan["Menü 1"], f"{week.from_date} {day.weekday}"
            assert vegan["Menü 2"], f"{week.from_date} {day.weekday}"


def test_sonderessen_overrides_prices(weeks):
    for week in weeks:
        for day in week.days:
            for meal in day.meals:
                if meal.sonderessen:
                    assert meal.price_internal == meal.price_external
                    assert meal.price_internal is not None
                    assert meal.price_internal != 6.0


def test_hyphenated_words_are_rejoined(weeks):
    donners = next(d for d in weeks[0].days if d.weekday == "Donnerstag")
    menue1 = next(m for m in donners.meals if m.type == "Menü 1")
    assert ("Gratinierte Hähnchenfilets a la Caprese mit Tomaten, "
            "Mozzarella dazu Kräuter-Knoblauch Baguette") == menue1.name


def test_names_are_whitespace_collapsed(weeks):
    for week in weeks:
        for day in week.days:
            for meal in day.meals:
                assert meal.name == " ".join(meal.name.split())


def test_no_header_or_footer_content_leaks_into_meals(weeks):
    forbidden = ("Partyservice", "Öffnungszeiten", "❖", "Zusatzstoffe", "E-Mail",
                 "www.Rolands", "Telefon", "06131", "0173", "Menü 1 u. 2")
    for week in weeks:
        for day in week.days:
            for meal in day.meals:
                for token in forbidden:
                    assert token not in meal.name


def test_weeks_validate(weeks):
    for week in weeks:
        week.validate()


def test_missing_date_range_raises():
    with pytest.raises(ValueError, match="Vom"):
        RolandSource().parse_page("Kein Datum hier\n   Montag\n   X\n")


def test_from_date_without_year_inherits_to_year():
    week = RolandSource().parse_page(_page("Vom 03.08. – 07.08.2026"))
    assert "2026-08-03" == week.from_date
    assert "2026-08-07" == week.to_date


def test_both_dates_with_years_cross_year_boundary():
    week = RolandSource().parse_page(_page("Vom 29.12.2025 – 02.01.2026"))
    assert "2025-12-29" == week.from_date
    assert "2026-01-02" == week.to_date


def test_no_menu_body_raises():
    with pytest.raises(ValueError, match="one meal per weekday"):
        RolandSource().parse_page("Vom 03.08. – 07.08.2026\nnur Kopfzeilen\n")


def test_missing_weekday_raises():
    text = _page("Vom 03.08. – 07.08.2026",
                 weekdays=("Montag", "Dienstag", "Mittwoch", "Donnerstag"))
    with pytest.raises(ValueError, match="one meal per weekday"):
        RolandSource().parse_page(text)


def test_parse_runs_pdftotext_and_returns_list_of_weeks():
    source = RolandSource()
    pdf_path = Path("/tmp/fake-roland.pdf")
    with mock.patch("mahlzeit.sources.roland.run_pdftotext",
                    return_value=FIXTURE.read_text(encoding="utf-8")) as run:
        weeks = source.parse([pdf_path])
    run.assert_called_once_with(pdf_path)
    assert 2 == len(weeks)
    assert ["2026-08-03", "2026-08-10"] == [w.from_date for w in weeks]


def test_extract_pdf_links_unescapes_dedupes_and_sorts():
    links = RolandSource()._extract_pdf_links(SAMPLE_HTML)
    assert 2 == len(links)
    assert "27.07-31.07.2026" in links[0]   # earlier week first
    assert "03.08.-14.08.2026" in links[1]
    for link in links:
        assert "%20" in link  # percent-encoding kept for the request
        assert "&amp;" not in link  # &amp; unescaped to &
        assert "not-a-menu" not in link


def test_link_date_range():
    source = RolandSource()
    assert ("2026-07-27", "2026-07-31") == source._link_date_range(
        "Speisenplan 27.07-31.07.2026.pdf"
    )
    assert ("2026-08-03", "2026-08-14") == source._link_date_range(
        "Speisenplan 03.08.-14.08.2026.pdf"
    )


def test_link_without_date_range_raises():
    with pytest.raises(ValueError, match="date range"):
        RolandSource()._link_date_range("Speisenplan.pdf")


def _urlopen(urls_to_data, order=None):
    """Mock urlopen returning `urls_to_data[full_url]` in call order."""
    opener = mock.MagicMock()
    order = list(urls_to_data) if order is None else order
    opener.side_effect = [urls_to_data[url] for url in order]
    return opener


def test_fetch_downloads_all_menu_pdfs_with_crawl_delay(tmp_path):
    pdf_a, pdf_b = PDF_BYTES + b"A", PDF_BYTES + b"B"
    urls = {
        PAGE_URL: _FakeResponse(SAMPLE_HTML.encode()),
        PDF_URL_A: _FakeResponse(pdf_a),
        PDF_URL_B: _FakeResponse(pdf_b),
    }
    opener = _urlopen(urls)
    with mock.patch("mahlzeit.sources.roland.urllib.request.urlopen", opener), \
         mock.patch("mahlzeit.sources.roland.time.sleep") as sleep:
        paths = RolandSource().fetch(tmp_path)

    assert 3 == opener.call_count
    assert 2 == sleep.call_count  # one delay per PDF request
    assert 2 == len(paths)
    for path in paths:
        assert path.is_file(), path
        assert path.read_bytes() in (pdf_a, pdf_b)
    assert {"Speisenplan BGHM Kantine 27.07-31.07.2026.pdf",
            "Speisenplan BGHM Kantine 03.08.-14.08.2026.pdf"} == {p.name for p in paths}


def test_fetch_skips_weeks_already_cached(tmp_path):
    target = tmp_path / "roland"
    target.mkdir(parents=True)
    (target / "Speisenplan BGHM Kantine 03.08.-14.08.2026.pdf").write_bytes(PDF_BYTES)
    (target / "Speisenplan BGHM Kantine 27.07-31.07.2026.pdf").write_bytes(PDF_BYTES)

    urls = {PAGE_URL: _FakeResponse(SAMPLE_HTML.encode())}
    opener = _urlopen(urls)
    with mock.patch("mahlzeit.sources.roland.urllib.request.urlopen", opener), \
         mock.patch("mahlzeit.sources.roland.time.sleep") as sleep:
        paths = RolandSource().fetch(tmp_path)

    assert 1 == opener.call_count  # only the HTML request
    assert 0 == sleep.call_count
    assert 2 == len(paths)
    for path in paths:
        assert PDF_BYTES == path.read_bytes()


def test_fetch_rejects_non_pdf_response(tmp_path):
    urls = {
        PAGE_URL: _FakeResponse(SAMPLE_HTML.encode()),
        PDF_URL_A: _FakeResponse(b"<html>not a pdf"),
    }
    opener = _urlopen(urls, order=[PAGE_URL, PDF_URL_A])
    with mock.patch("mahlzeit.sources.roland.urllib.request.urlopen", opener), \
         mock.patch("mahlzeit.sources.roland.time.sleep"):
        with pytest.raises(RuntimeError, match="did not return a PDF"):
            RolandSource().fetch(tmp_path)


def _page(date_line, weekdays=("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")):
    """Craft a minimal valid page (prices + weekday blocks with 2 meals)."""
    lines = ["Kopfzeile", date_line]
    lines.append("Menü 1")
    lines.append("Interne Gäste 6,00 €")
    lines.append("Externe Gäste 8,00 €")
    for index, weekday in enumerate(weekdays):
        lines.append(weekday)
        left = f"Gericht {index + 1} (a1|2, c, d, k, m)"
        right = f"Beilage {index + 1} (a1|2, c, d, k, m)"
        lines.append(left.ljust(95) + right)
    return "\n".join(lines)
