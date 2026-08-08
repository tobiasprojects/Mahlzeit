"""Command-line interface: `refresh` and `serve`.

- `refresh` — for each source in the registry (or a `--source` subset): `fetch()`
  → `parse()` → merge into one `Menu` → write `data/menus.json`. Each source runs
  in isolation: an exception is logged and the next source still runs, so one bad
  source never kills the run.
- `serve` — static HTTP server over `web/` (site root) plus `data/` under
  `/data/`, so the dashboard can fetch `data/menus.json` same-origin.
"""

from __future__ import annotations

import argparse
import http.server
import logging
import posixpath
import sys
from pathlib import Path
from typing import List, Optional

from .model import Menu, Restaurant
from .registry import all_sources, get_source
from .store import keep_weeks, write_menus

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MENUS_PATH = DATA_DIR / "menus.json"
WEB_DIR = REPO_ROOT / "web"


def refresh(source_ids: Optional[List[str]] = None) -> int:
    """Fetch + parse every requested source and write a fresh `menus.json`."""
    if source_ids:
        sources = [get_source(source_id) for source_id in source_ids]
    else:
        sources = all_sources()

    menu = Menu(generated_at="", restaurants=[])
    for source in sources:
        try:
            pdfs = source.fetch(RAW_DIR)
            weeks = source.parse(pdfs)
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            logger.error("source %s failed: %s", source.id, exc)
            continue
        restaurant = Restaurant(
            id=source.id,
            name=source.name,
            source_url=source.source_url,
            weeks=weeks,
        )
        keep_weeks(restaurant)
        menu.restaurants.append(restaurant)
        logger.info("source %s: %d week(s)", source.id, len(restaurant.weeks))

    if not menu.restaurants:
        logger.error("no sources produced a menu; nothing written")
        return 1

    write_menus(MENUS_PATH, menu)
    logger.info("wrote %s (%d restaurant(s))", MENUS_PATH, len(menu.restaurants))
    return 0


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves `web/` as the site root and `data/` under `/data/`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def translate_path(self, path: str) -> str:
        if path.startswith("/data/"):
            words = posixpath.normpath(path[len("/data/"):]).split("/")
            words = [word for word in words if word not in ("", ".", "..")]
            return str(DATA_DIR.joinpath(*words))
        return super().translate_path(path)


def serve(host: str = "127.0.0.1", port: int = 8000) -> int:
    server = http.server.ThreadingHTTPServer((host, port), _Handler)
    logger.info(
        "serving %s and %s on http://%s:%d", WEB_DIR, DATA_DIR, host, port
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mahlzeit",
        description="Sync weekly canteen menus from restaurant PDFs to a static dashboard.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    refresh_parser = sub.add_parser(
        "refresh", help="download + parse all sources, write data/menus.json"
    )
    refresh_parser.add_argument(
        "--source",
        action="append",
        dest="source_ids",
        metavar="ID",
        help="only refresh this source (repeatable, e.g. --source vaihingen)",
    )

    serve_parser = sub.add_parser(
        "serve", help="serve web/ + data/ over HTTP for the dashboard"
    )
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="bind port (default: 8000)"
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "refresh":
        return refresh(args.source_ids)
    return serve(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
