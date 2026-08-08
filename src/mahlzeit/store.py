"""Read/write data/menus.json (+ metadata).

The serialized format follows PROJECT.md §4. `generated_at` is written with a
local timezone offset (e.g. `2026-08-07T22:00:00+02:00`) so the frontend can show
when the data was last fetched. Writes are atomic (tmp file + rename), so a
crashed refresh never leaves a half-written `menus.json`.

The week-retention policy defaults to "current + next week only" (open decision
§9): `keep_weeks` drops anything older than the current week or further out than
the next one. History archiving is a later enhancement.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Union

from .model import Menu, Restaurant

PathLike = Union[str, Path]


def now_iso() -> str:
    """Current local time as ISO-8601 with tz offset, no microseconds."""
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def read_menus(path: PathLike) -> Menu:
    """Load a `Menu` from JSON; return an empty menu if the file is missing."""
    path = Path(path)
    if not path.is_file():
        return Menu(generated_at=now_iso(), restaurants=[])
    data = json.loads(path.read_text(encoding="utf-8"))
    return Menu.from_dict(data)


def write_menus(path: PathLike, menu: Menu) -> None:
    """Pretty-print `menu` to `path` atomically (tmp + rename).

    `generated_at` is refreshed to now with the local tz offset. The menu is
    validated first, so an invalid model is never written to disk.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    menu.generated_at = now_iso()
    menu.validate()
    payload = json.dumps(menu.to_dict(), indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def keep_weeks(restaurant: Restaurant, today: Optional[dt.date] = None) -> Restaurant:
    """Keep only the current and the next week; drop the rest (§9 default).

    Weeks overlapping the 14-day window starting on the Monday of the current
    week survive; older and further-out weeks are removed. `restaurant` is
    mutated in place and returned for convenience.
    """
    today = today if today is not None else dt.date.today()
    current_monday = today - dt.timedelta(days=today.weekday())
    window_start = current_monday
    window_end = current_monday + dt.timedelta(days=13)
    kept = []
    for week in restaurant.weeks:
        from_date = dt.date.fromisoformat(week.from_date)
        to_date = dt.date.fromisoformat(week.to_date)
        if to_date >= window_start and from_date <= window_end:
            kept.append(week)
    restaurant.weeks = kept
    return restaurant
