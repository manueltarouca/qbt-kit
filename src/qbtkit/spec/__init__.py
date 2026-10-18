"""Endpoint spec. Importing a scope module registers its endpoints."""

from __future__ import annotations

from ._types import Endpoint, all_endpoints

_SCOPES = (
    "torrents",
    "app",
    "transfer",
    "sync",
    "log",
    "auth",
    "rss",
    "search",
    "torrentcreator",
    "clientdata",
)
# grows as scopes land; see docs/ROADMAP.md


def load_all() -> list[Endpoint]:
    """Import every scope module, then return the registry contents."""
    from importlib import import_module

    for scope in _SCOPES:
        import_module(f"{__name__}.{scope}")
    return all_endpoints()


__all__ = ["Endpoint", "all_endpoints", "load_all"]
