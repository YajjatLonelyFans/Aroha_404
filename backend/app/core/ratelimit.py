"""Small in-process sliding-window limiters (one backend process in the demo)."""

import time
from collections import deque
from collections.abc import Callable

from app.core.errors import AppError


class RateLimited(AppError):
    def __init__(self, retry_after_s: int, scope: str = "you") -> None:
        who = "Too many messages" if scope == "you" else "The assistant is busy"
        super().__init__(
            "rate_limited",
            f"{who} right now. Try again in about {retry_after_s} seconds.",
            status_code=429,
            retryable=True,
            details={"retry_after_s": retry_after_s, "scope": scope},
        )


class SlidingWindowLimiter:
    """At most `max_events` per key in any `window_s`. Idle keys are pruned, so memory stays bounded."""

    def __init__(self, max_events: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._max = max_events
        self._window = window_s
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def _prune(self, now: float) -> None:
        for key in [k for k, ev in self._events.items() if not ev or now - ev[-1] >= self._window]:
            del self._events[key]

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may act again, or None if it may act now. Records nothing."""
        now = self._clock()
        events = self._events.get(key)
        if events:
            while events and now - events[0] >= self._window:
                events.popleft()
            if len(events) >= self._max:
                return max(1, round(self._window - (now - events[0])))
        return None

    def record(self, key: str) -> None:
        now = self._clock()
        if len(self._events) > 1000:
            self._prune(now)
        self._events.setdefault(key, deque()).append(now)

    def check(self, key: str) -> None:
        wait = self.retry_after(key)
        if wait is not None:
            raise RateLimited(wait)
        self.record(key)

    def __len__(self) -> int:
        return len(self._events)


class ChatLimiter:
    """Per-user limit plus an overall cap, so neither one user nor many users can drain the LLM quota."""

    def __init__(self, per_user: int, total: int, window_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._user = SlidingWindowLimiter(per_user, window_s, clock)
        self._total = SlidingWindowLimiter(total, window_s, clock)

    def check(self, user_id: str) -> None:
        wait = self._user.retry_after(user_id)
        if wait is not None:
            raise RateLimited(wait)
        wait = self._total.retry_after("*")
        if wait is not None:
            raise RateLimited(wait, scope="everyone")
        self._user.record(user_id)
        self._total.record("*")
