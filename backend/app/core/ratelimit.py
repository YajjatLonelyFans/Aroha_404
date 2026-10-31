"""Small in-process sliding-window limiter (one backend process in the demo)."""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from app.core.errors import AppError


class RateLimited(AppError):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(
            "rate_limited",
            f"Too many messages in a minute. Try again in about {retry_after_s} seconds.",
            status_code=429,
            retryable=True,
            details={"retry_after_s": retry_after_s},
        )


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._max = max_events
        self._window = window_s
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Record one event for `key`, or raise RateLimited if the window is full."""
        now = self._clock()
        events = self._events[key]
        while events and now - events[0] >= self._window:
            events.popleft()
        if len(events) >= self._max:
            raise RateLimited(max(1, round(self._window - (now - events[0]))))
        events.append(now)
