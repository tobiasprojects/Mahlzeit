"""Source interface (fetch + parse contract) + shared pdftotext helper.

Each restaurant is one `Source` subclass (PROJECT.md §2.1). Subclasses own all
restaurant-specific knowledge: URL discovery, cache-buster handling, crawl
politeness and the PDF layout parser. `run_pdftotext` is the only shared piece —
zero third-party deps, shell out to poppler's `pdftotext -layout`.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from ..model import Week


class Source(ABC):
    """Plugin contract: stable identity + fetch/parse.

    Subclasses set the class attributes and implement `fetch()`/`parse()`. One
    instance per source is registered in `SOURCES`, keyed by `id`.
    """

    id: str = ""
    name: str = ""
    source_url: str = ""

    @abstractmethod
    def fetch(self, cache_dir: Path) -> List[Path]:
        """Download raw PDFs into `cache_dir` and return their local paths.

        Sources discover their own URLs (fixed URL, or scraping an HTML page for
        current links) and handle cache-busters. Skip files whose local copy
        already exists.
        """

    @abstractmethod
    def parse(self, pdf_paths: List[Path]) -> List[Week]:
        """Convert the downloaded PDFs into unified `Week`s."""


def run_pdftotext(path: Path) -> str:
    """Extract text via `pdftotext -layout <path> -`; raise on non-zero exit."""
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"pdftotext failed on {path}: {stderr or f'exit code {result.returncode}'}"
        )
    return result.stdout
