"""Cache utilities for key-value lookup and TTL management."""

import time


CACHE_TTL_SECONDS = 300


class Cache:
    """A simple in-memory key-value cache with TTL support."""

    def __init__(self):
        self._store = {}
        self._timestamps = {}

    def get(self, key):
        """Return cached value for key, or None if missing or expired."""
        if key not in self._store:
            return None
        age = time.time() - self._timestamps.get(key, 0)
        if age > CACHE_TTL_SECONDS:
            return None
        return self._store[key]
