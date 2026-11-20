"""In-process TTL cache with single-flight de-duplication.

Concurrent requests for the same key share one upstream call, so a burst of
users asking about "Paris" triggers a single geocode + weather fetch.
No Redis required.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

_MISS = object()


class TTLCache:
    def __init__(self, max_items: int = 2048) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._max = max_items
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return _MISS
        expires, value = entry
        if expires < time.monotonic():
            self._data.pop(key, None)
            return _MISS
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        if len(self._data) >= self._max:
            self._evict()
        self._data[key] = (time.monotonic() + ttl, value)

    def _evict(self) -> None:
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._data.items() if exp < now]:
            del self._data[k]
        while len(self._data) >= self._max:  # drop oldest insertions
            self._data.pop(next(iter(self._data)))

    async def get_or_set(
        self, key: str, ttl: float, factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        value = self.get(key)
        if value is not _MISS:
            self.hits += 1
            return value
        self.misses += 1

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(factory())
            self._inflight[key] = task
            task.add_done_callback(lambda _t, k=key: self._inflight.pop(k, None))
        # shield: one impatient caller disconnecting must not kill the shared fetch
        value = await asyncio.shield(task)
        self.set(key, value, ttl)
        return value

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "items": len(self._data),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }


cache = TTLCache()
