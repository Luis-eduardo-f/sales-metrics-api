"""A tiny in-process cache-aside helper used by the `/metrics/revenue` endpoint.

Why cache an analytics endpoint at all? Revenue aggregation scans every order item in the
requested date range and groups it in Python -- cheap for a demo dataset, but the kind of
query that gets expensive fast on a real warehouse table, and analytics dashboards tend to
poll the same handful of (group_by, start_date, end_date) combinations repeatedly (e.g. a
"last 30 days" widget refreshed every few seconds by several users). A short-lived cache
turns those repeated identical requests into a dict lookup instead of a full aggregation.

This uses `cachetools.TTLCache`, an in-memory, per-process, least-recently-used cache with a
time-to-live per entry -- intentionally simple so the project has zero external infrastructure
requirements. It is **not** shared across multiple API processes/replicas. The natural
production upgrade path (documented in the README) is swapping this module's implementation
for a Redis-backed cache (e.g. via `redis-py` + a `SET ... EX <ttl>` / `GET`), which gives you
a shared cache across replicas without changing any call site -- every consumer of this module
only depends on `cache_get` / `cache_set`, not on `TTLCache` itself.
"""

from typing import Any

from cachetools import TTLCache

from app.config import get_settings

_settings = get_settings()

# maxsize bounds memory usage (LRU eviction once full); ttl bounds staleness.
_cache: TTLCache = TTLCache(maxsize=256, ttl=_settings.cache_ttl_seconds)


def make_cache_key(*parts: Any) -> tuple:
    """Build a hashable cache key from arbitrary request parameters."""

    return tuple(parts)


def cache_get(key: tuple) -> Any | None:
    """Return the cached value for `key`, or None on a cache miss (or expiry)."""

    return _cache.get(key)


def cache_set(key: tuple, value: Any) -> None:
    """Store `value` under `key`, subject to the cache's TTL and max size."""

    _cache[key] = value


def cache_clear() -> None:
    """Clear the entire cache. Mainly useful for tests."""

    _cache.clear()
