"""Unified schema + validation for menus (PROJECT.md §4).

Everything serializes to plain JSON-compatible dicts. Dates and datetimes are kept
as ISO-8601 strings in the data (e.g. "2026-08-03", "2026-08-07T22:00:00+02:00") so
the frontend can compute today/upcoming/expired purely client-side.

Optional fields (prices, allergens, `sonderessen`) are omitted from the serialized
dict when absent, matching the §4 example; `type`, `name` and `vegan` are always
present. `Week` uses `from_date`/`to_date` as attribute names (`from` is a keyword)
and maps them to the JSON keys `from`/`to`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _require_non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string, got {value!r}")
    return value


def _parse_date(value: Any, label: str) -> dt.date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string, got {value!r}")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid ISO date: {value!r}") from exc


def _parse_datetime(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO datetime string, got {value!r}")
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid ISO datetime: {value!r}") from exc


def _optional_float(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number, got {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number, got {value!r}") from None


def _as_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object, got {value!r}")
    return value


@dataclass
class Meal:
    """A single dish. Only `type`, `name` and `vegan` are required."""

    type: str
    name: str
    vegan: bool = False
    price_internal: Optional[float] = None
    price_external: Optional[float] = None
    allergens: Optional[str] = None
    sonderessen: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "Meal":
        d = _as_dict(data, "meal")
        return cls(
            type=_require_non_empty(d.get("type"), "meal.type"),
            name=_require_non_empty(d.get("name"), "meal.name"),
            vegan=bool(d.get("vegan", False)),
            price_internal=_optional_float(d.get("price_internal"), "meal.price_internal"),
            price_external=_optional_float(d.get("price_external"), "meal.price_external"),
            allergens=d.get("allergens"),
            sonderessen=bool(d.get("sonderessen", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": self.type, "name": self.name, "vegan": self.vegan}
        if self.price_internal is not None:
            out["price_internal"] = self.price_internal
        if self.price_external is not None:
            out["price_external"] = self.price_external
        if self.allergens is not None:
            out["allergens"] = self.allergens
        if self.sonderessen:
            out["sonderessen"] = True
        return out

    def validate(self) -> None:
        _require_non_empty(self.type, "meal.type")
        _require_non_empty(self.name, "meal.name")
        if self.allergens is not None and not isinstance(self.allergens, str):
            raise ValueError(f"meal.allergens must be a string or None, got {self.allergens!r}")
        for attr in ("price_internal", "price_external"):
            value = getattr(self, attr)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                raise ValueError(f"meal.{attr} must be a non-negative number, got {value!r}")


@dataclass
class Day:
    """A single day of a week: ISO `date`, German `weekday`, `meals`."""

    date: str
    weekday: str
    meals: List[Meal]

    @classmethod
    def from_dict(cls, data: Any) -> "Day":
        d = _as_dict(data, "day")
        return cls(
            date=_parse_date(d.get("date"), "day.date").isoformat(),
            weekday=_require_non_empty(d.get("weekday"), "day.weekday"),
            meals=[Meal.from_dict(m) for m in d.get("meals", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "weekday": self.weekday,
            "meals": [m.to_dict() for m in self.meals],
        }

    def validate(self) -> None:
        _parse_date(self.date, "day.date")
        _require_non_empty(self.weekday, "day.weekday")
        if not self.meals:
            raise ValueError(f"day {self.date} has no meals")
        for meal in self.meals:
            meal.validate()


@dataclass
class Week:
    """A menu week: `from_date`/`to_date` (ISO), plus `days`.

    Serialized with the JSON keys `from`/`to` (PROJECT.md §4).
    """

    from_date: str
    to_date: str
    days: List[Day]

    @classmethod
    def from_dict(cls, data: Any) -> "Week":
        d = _as_dict(data, "week")
        return cls(
            from_date=_parse_date(d.get("from"), "week.from").isoformat(),
            to_date=_parse_date(d.get("to"), "week.to").isoformat(),
            days=[Day.from_dict(day) for day in d.get("days", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_date,
            "to": self.to_date,
            "days": [d.to_dict() for d in self.days],
        }

    def validate(self) -> None:
        start = _parse_date(self.from_date, "week.from")
        end = _parse_date(self.to_date, "week.to")
        if end < start:
            raise ValueError(
                f"week.to ({self.to_date}) is before week.from ({self.from_date})"
            )
        if not self.days:
            raise ValueError(f"week {self.from_date}..{self.to_date} has no days")
        for day in self.days:
            day.validate()
            day_date = _parse_date(day.date, "day.date")
            if not start <= day_date <= end:
                raise ValueError(
                    f"day {day.date} is outside week {self.from_date}..{self.to_date}"
                )


@dataclass
class Restaurant:
    """A menu provider: stable `id`, display `name`, `source_url`, `weeks`."""

    id: str
    name: str
    source_url: str
    weeks: List[Week]

    @classmethod
    def from_dict(cls, data: Any) -> "Restaurant":
        d = _as_dict(data, "restaurant")
        return cls(
            id=_require_non_empty(d.get("id"), "restaurant.id"),
            name=_require_non_empty(d.get("name"), "restaurant.name"),
            source_url=_require_non_empty(d.get("source_url"), "restaurant.source_url"),
            weeks=[Week.from_dict(w) for w in d.get("weeks", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source_url": self.source_url,
            "weeks": [w.to_dict() for w in self.weeks],
        }

    def validate(self) -> None:
        _require_non_empty(self.id, "restaurant.id")
        _require_non_empty(self.name, "restaurant.name")
        _require_non_empty(self.source_url, "restaurant.source_url")
        for week in self.weeks:
            week.validate()


@dataclass
class Menu:
    """Root container: `generated_at` (ISO datetime) + `restaurants`."""

    generated_at: str
    restaurants: List[Restaurant]

    @classmethod
    def from_dict(cls, data: Any) -> "Menu":
        d = _as_dict(data, "menu")
        return cls(
            generated_at=_require_non_empty(d.get("generated_at"), "menu.generated_at"),
            restaurants=[Restaurant.from_dict(r) for r in d.get("restaurants", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "restaurants": [r.to_dict() for r in self.restaurants],
        }

    def validate(self) -> None:
        _parse_datetime(self.generated_at, "menu.generated_at")
        seen: set[str] = set()
        for restaurant in self.restaurants:
            restaurant.validate()
            if restaurant.id in seen:
                raise ValueError(f"duplicate restaurant id: {restaurant.id!r}")
            seen.add(restaurant.id)
