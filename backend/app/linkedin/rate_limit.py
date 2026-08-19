"""Simple in-memory per-user rate limiter for profile extraction."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Fixed-window sliding counter: max_calls per window_seconds per key."""

    def __init__(self, max_calls: int = 10, window_seconds: int = 3600) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, str]:
        """Return (allowed, message). Records a hit when allowed."""
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
                    f"Rate limit exceeded ({self.max_calls} extractions/hour). "
                    f"Try again in ~{max(retry_in, 1)}s.",
                )
            q.append(now)
            return True, "ok"


# Module-level limiter shared by routes (10 extracts / user / hour).
profile_extract_limiter = RateLimiter(max_calls=10, window_seconds=3600)

# Bulk Excel uploads: 5 jobs / user / hour.
bulk_extract_limiter = RateLimiter(max_calls=5, window_seconds=3600)
