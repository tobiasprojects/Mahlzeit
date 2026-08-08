"""Source plugins — one module per restaurant (auto-discovered).

Adding a restaurant is a single new module in this package implementing `Source`
(PROJECT.md §2.1); no registry edits needed. Discovery imports every module in
this package and collects the `Source` subclasses defined in it, keyed by `id`.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Optional, Sequence

from .base import Source

__all__ = ["SOURCES", "discover_sources"]


def discover_sources(
    package_path: Optional[Sequence[str]] = None,
    module_prefix: Optional[str] = None,
) -> Dict[str, Source]:
    """Import all modules in a package directory and collect their `Source` subclasses.

    Defaults to this package (import-time discovery). `package_path` and
    `module_prefix` are overridable so tests can exercise discovery against a
    throwaway package without touching the real one.
    """
    if package_path is None:
        package_path = __path__
    if module_prefix is None:
        module_prefix = __name__
    sources: Dict[str, Source] = {}
    for module_info in pkgutil.iter_modules(package_path):
        module = importlib.import_module(f"{module_prefix}.{module_info.name}")
        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type) or obj is Source or not issubclass(obj, Source):
                continue
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            instance = obj()
            if not instance.id:
                continue
            if instance.id in sources:
                raise RuntimeError(f"duplicate source id: {instance.id!r}")
            sources[instance.id] = instance
    return sources


SOURCES: Dict[str, Source] = discover_sources()
