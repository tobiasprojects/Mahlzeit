"""Source registry: source id -> plugin instance.

Backed by the auto-discovered `SOURCES` dict from `sources/__init__.py`. Shared
code (CLI, store, frontend) only ever talks to the registry, never to a concrete
source — so adding a restaurant never touches shared code (§2.1).
"""

from __future__ import annotations

from typing import List

from .sources import SOURCES
from .sources.base import Source


def get_source(source_id: str) -> Source:
    try:
        return SOURCES[source_id]
    except KeyError:
        raise KeyError(
            f"unknown source {source_id!r}; available: {', '.join(sorted(SOURCES))}"
        ) from None


def all_sources() -> List[Source]:
    """All discovered source instances (one per restaurant)."""
    return list(SOURCES.values())
