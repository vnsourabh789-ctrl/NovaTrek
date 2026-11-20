"""Tiny sliding-window rate limiter (per client key)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        if len(self._hits) > 10_000:  # bound memory under scans
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                del self._hits[k]
        return True
