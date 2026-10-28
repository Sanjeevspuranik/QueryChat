import asyncio
import time
from collections import OrderedDict

from app.adapters.base import DatabaseAdapter
from app.adapters.registry import AdapterRegistry


class AdapterPool:
    """LRU cache of connected adapters keyed by connection id.

    A per-key lock prevents duplicate engines under concurrent requests; idle and
    over-capacity entries are closed so users cannot exhaust file descriptors."""

    def __init__(self, registry: AdapterRegistry, max_size: int, idle_seconds: int) -> None:
        self._registry = registry
        self._max_size = max_size
        self._idle_seconds = idle_seconds
        self._entries: OrderedDict[str, tuple[DatabaseAdapter, float]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    async def acquire(self, key: str, url: str) -> DatabaseAdapter:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(key)
            if entry is not None:
                adapter = entry[0]
            else:
                adapter = self._registry.create(url)
                await adapter.connect()
            self._entries[key] = (adapter, time.monotonic())
            self._entries.move_to_end(key)
        await self._evict_excess()
        return adapter

    async def evict(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        self._locks.pop(key, None)
        if entry is not None:
            await entry[0].close()

    async def _evict_excess(self) -> None:
        now = time.monotonic()
        stale = [k for k, (_, used) in self._entries.items() if now - used > self._idle_seconds]
        for key in stale:
            await self.evict(key)
        while len(self._entries) > self._max_size:
            await self.evict(next(iter(self._entries)))

    async def close_all(self) -> None:
        for key in list(self._entries):
            await self.evict(key)
