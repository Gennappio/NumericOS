"""Wake-up signal from committing threads to async subscribers. It carries no data.

Truth is always re-read from the ledger by cursor, so there is no queue, no fan-out buffer and no
ordering problem across threads. One instance per process (``uvicorn --workers 1``).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager

Subscriber = tuple[asyncio.AbstractEventLoop, asyncio.Event]


class EventNotifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[Subscriber]] = {}

    @contextmanager
    def subscribe(self, project_id: str) -> Iterator[asyncio.Event]:
        """Register the running event loop; the yielded Event is set after each commit."""
        key: Subscriber = (asyncio.get_running_loop(), asyncio.Event())
        with self._lock:
            self._subscribers.setdefault(project_id, set()).add(key)
        try:
            yield key[1]
        finally:
            with self._lock:
                subscribers = self._subscribers.get(project_id)
                if subscribers is not None:
                    subscribers.discard(key)
                    if not subscribers:
                        del self._subscribers[project_id]

    def publish(self, project_id: str, seq: int) -> None:
        """Called by the committing thread *after* a durable commit. Safe from any thread."""
        with self._lock:
            targets = list(self._subscribers.get(project_id, ()))
        for loop, wake in targets:
            if not loop.is_closed():
                loop.call_soon_threadsafe(wake.set)

    def subscriber_count(self, project_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(project_id, ()))
