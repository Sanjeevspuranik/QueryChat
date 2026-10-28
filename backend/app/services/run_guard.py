import asyncio
import time
from collections import defaultdict, deque

from app.core.errors import ConflictError, RateLimitError


class RunGuard:
    """Backpressure for agent runs: global, per-user, per-connection and
    one-active-run-per-session limits. In-process; swap for Redis when scaling out."""

    def __init__(self, max_global: int, max_per_user: int, max_per_connection: int, stale_seconds: int) -> None:
        self._max_global = max_global
        self._max_per_user = max_per_user
        self._max_per_connection = max_per_connection
        self._stale_seconds = stale_seconds
        self._runs: dict[str, tuple[str, str, float]] = {}  # session -> (user, connection, started)

    def acquire(self, session_id: str, user_id: str, connection_id: str) -> None:
        self._drop_stale()
        if session_id in self._runs:
            raise ConflictError("This chat already has a request in progress.")
        runs = list(self._runs.values())
        if (
            len(runs) >= self._max_global
            or sum(1 for u, _, _ in runs if u == user_id) >= self._max_per_user
            or sum(1 for _, c, _ in runs if c == connection_id) >= self._max_per_connection
        ):
            raise RateLimitError("Too many requests in progress. Please retry shortly.")
        self._runs[session_id] = (user_id, connection_id, time.monotonic())

    def release(self, session_id: str) -> None:
        self._runs.pop(session_id, None)

    def _drop_stale(self) -> None:
        now = time.monotonic()
        for sid in [s for s, (_, _, t) in self._runs.items() if now - t > self._stale_seconds]:
            del self._runs[sid]


class SlidingWindowLimiter:
    """Simple per-key attempt limiter (used for login throttling)."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        async with self._lock:
            now = time.monotonic()
            hits = self._hits[key]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= self._max:
                raise RateLimitError("Too many attempts. Try again later.")
            hits.append(now)

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._hits.pop(key, None)
