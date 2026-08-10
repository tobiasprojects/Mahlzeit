"""Tests for the static web pages and their cross-links.

The frontend must always link the legal pages (Impressum, Datenschutz) from the
footer so they are reachable once deployed. The Impressum itself is only
generated in CI from a secret and is not part of the repo, so only the *link*
is verified here.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"


def _read_web(name: str) -> str:
    path = WEB_DIR / name
    assert path.exists(), f"missing {path}"
    return path.read_text()


def test_footer_links_legal_pages_from_index():
    index = _read_web("index.html")
    for page in ("impressum.html", "datenschutz.html"):
        assert f'href="{page}"' in index


def test_datenschutz_links_back_and_to_impressum():
    datenschutz = _read_web("datenschutz.html")
    assert 'href="index.html"' in datenschutz
    assert 'href="impressum.html"' in datenschutz


def test_legal_pages_share_stylesheet():
    for page in ("impressum.html", "datenschutz.html"):
        if not (WEB_DIR / page).exists():
            continue
        assert "style.css" in _read_web(page)
