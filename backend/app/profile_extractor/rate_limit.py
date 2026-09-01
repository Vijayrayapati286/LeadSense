"""Simple per-user rate limiter for profile extraction."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int = 20, window_seconds: int = 3600) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, str]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_calls:
                retry_in = int(self.window_seconds - (now - q[0])) + 1
                return (
                    False,
                    f"Rate limit exceeded ({self.max_calls}/hour). Try again in ~{max(retry_in, 1)}s.",
                )
            q.append(now)
            return True, "ok"


profile_extract_limiter = RateLimiter(max_calls=20, window_seconds=3600)
