"""In-memory rate limits. Daily turns and IELTS reviews use separate budgets."""

from __future__ import annotations

import time


class RateLimiter:
    def __init__(self) -> None:
        self.events: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: float) -> tuple[bool, int]:
        now = time.monotonic()
        kept = [stamp for stamp in self.events.get(key, []) if now - stamp < window_seconds]
        if len(kept) >= limit:
            self.events[key] = kept
            retry = int(window_seconds - (now - kept[0])) + 1
            return False, max(1, retry)
        kept.append(now)
        self.events[key] = kept
        return True, 0

    def reset(self) -> None:
        self.events.clear()


LIMITER = RateLimiter()
