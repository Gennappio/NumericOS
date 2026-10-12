"""Replay-then-live iteration over a project's ledger.

The notifier only wakes the loop up; every event comes from a ledger read by cursor. So a
subscriber never sees anything that is not durable and never misses anything that is:

- the wake flag is cleared *before* each read, so a commit that lands during the read leaves it
  set and the next wait returns at once;
- a wait also ends after ``heartbeat`` seconds, which bounds the delay for events committed by
  another process (which cannot wake this one) to one heartbeat.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress

from numericos.core.schemas import EventOut, EventPage
from numericos.events.notifier import EventNotifier

#: Reads one page of events with ``seq`` greater than the given cursor, in ``seq`` order.
ReadAfter = Callable[[int], Awaitable[EventPage]]


async def follow(
    notifier: EventNotifier,
    project_id: str,
    read_after: ReadAfter,
    cursor: int,
    *,
    heartbeat: float,
) -> AsyncGenerator[EventOut, None]:
    """Yield every event after ``cursor`` in order, then each new one as it is committed."""
    with notifier.subscribe(project_id) as wake:
        while True:
            wake.clear()
            page = await read_after(cursor)
            for event in page.events:
                cursor = event.seq
                yield event
            if page.has_more:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), timeout=heartbeat)
