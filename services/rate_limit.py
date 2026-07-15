from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque


@dataclass
class RateLimitExceeded(Exception):
    retry_after: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._buckets: dict[str, Deque[float]] = defaultdict(deque)
        self._bucket_windows: dict[str, int] = {}
        self._last_cleanup = time.monotonic()

    def hit(self, scope: str, key: str, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            return

        now = time.monotonic()
        bucket_key = f"{scope}:{key}"
        with self._guard:
            bucket = self._buckets[bucket_key]
            self._bucket_windows[bucket_key] = window_seconds
            self._drop_expired(bucket, now, window_seconds)
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimitExceeded(retry_after=retry_after)
            bucket.append(now)
            self._cleanup(now)

    @staticmethod
    def _drop_expired(bucket: Deque[float], now: float, window_seconds: int) -> None:
        while bucket and now - bucket[0] >= window_seconds:
            bucket.popleft()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        empty_keys = []
        for key, bucket in self._buckets.items():
            self._drop_expired(bucket, now, self._bucket_windows.get(key, 60))
            if not bucket:
                empty_keys.append(key)
        for key in empty_keys:
            self._buckets.pop(key, None)
            self._bucket_windows.pop(key, None)


rate_limiter = InMemoryRateLimiter()
