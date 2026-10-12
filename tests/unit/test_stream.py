"""`follow()`: replay by cursor, then live, with no lost and no undurable events."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

from numericos.core.schemas import EventOut, EventPage
from numericos.events.notifier import EventNotifier
from numericos.events.stream import follow

PROJECT = "prj_1"
LONG = 60.0  # a heartbeat that never fires inside a test: only a wake-up can deliver


def event(seq: int) -> EventOut:
    return EventOut(
        event_id=f"evt_{seq}",
        seq=seq,
        project_id=PROJECT,
        type="CARD_CREATED",
        subject_id="card_1",
        actor="test:unit",
        producer="api",
        severity="info",
        correlation_id="cor_1",
        schema_version=1,
        timestamp_utc=datetime(2026, 10, 12, tzinfo=UTC),
        payload={},
    )


class Ledger:
    """An in-memory ledger read the way the API reads the real one: by cursor, in pages."""

    def __init__(self, *seqs: int, page_size: int = 500) -> None:
        self.seqs = list(seqs)
        self.page_size = page_size
        self.reads: list[int] = []
        self.on_read: Callable[[], None] | None = None

    async def read_after(self, cursor: int) -> EventPage:
        self.reads.append(cursor)
        newer = [seq for seq in self.seqs if seq > cursor]
        page = newer[: self.page_size]
        if self.on_read is not None:
            hook, self.on_read = self.on_read, None
            hook()  # something commits after the rows were read and before the wait
        return EventPage(
            events=[event(seq) for seq in page],
            next_cursor=page[-1] if page else None,
            has_more=len(newer) > self.page_size,
        )


async def take(stream: Awaitable[EventOut], timeout: float = 2.0) -> int:
    return (await asyncio.wait_for(stream, timeout)).seq


def test_replays_after_the_cursor_then_delivers_new_commits() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1, 2, 3)
        stream = follow(notifier, PROJECT, ledger.read_after, 1, heartbeat=LONG)

        assert [await take(anext(stream)), await take(anext(stream))] == [2, 3]

        waiting = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.05)
        assert not waiting.done()  # nothing is invented while the ledger is quiet

        ledger.seqs.append(4)
        notifier.publish(PROJECT, 4)
        assert await take(waiting) == 4
        await stream.aclose()

    asyncio.run(scenario())


def test_a_commit_that_lands_during_a_read_is_not_lost() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1)

        def commit_between_read_and_wait() -> None:
            ledger.seqs.append(2)
            notifier.publish(PROJECT, 2)

        # The first read returns event 1; event 2 is committed right after its rows were read.
        ledger.on_read = commit_between_read_and_wait
        stream = follow(notifier, PROJECT, ledger.read_after, 0, heartbeat=LONG)
        assert await take(anext(stream)) == 1

        # With a 60 s heartbeat only the wake flag can deliver event 2. It survives because the
        # flag is cleared *before* each read: clearing it afterwards would erase this commit.
        assert await take(anext(stream)) == 2
        assert ledger.reads == [0, 1]
        await stream.aclose()

    asyncio.run(scenario())


def test_a_long_backlog_is_replayed_page_by_page_without_waiting() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1, 2, 3, 4, 5, page_size=2)
        stream = follow(notifier, PROJECT, ledger.read_after, 0, heartbeat=LONG)

        assert [await take(anext(stream)) for _ in range(5)] == [1, 2, 3, 4, 5]
        assert ledger.reads == [0, 2, 4]
        await stream.aclose()

    asyncio.run(scenario())


def test_the_heartbeat_finds_events_nobody_announced() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1)
        stream = follow(notifier, PROJECT, ledger.read_after, 0, heartbeat=0.05)
        assert await take(anext(stream)) == 1

        ledger.seqs.append(2)  # committed by another process: no publish() reaches this one

        assert await take(anext(stream)) == 2
        await stream.aclose()

    asyncio.run(scenario())


def test_commits_of_other_projects_do_not_cause_reads() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1)
        stream = follow(notifier, PROJECT, ledger.read_after, 1, heartbeat=LONG)
        waiting = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.05)
        reads = len(ledger.reads)

        notifier.publish("prj_other", 7)
        await asyncio.sleep(0.05)

        assert len(ledger.reads) == reads
        assert not waiting.done()
        waiting.cancel()
        with suppress(asyncio.CancelledError):
            await waiting

    asyncio.run(scenario())


def test_closing_or_cancelling_the_stream_unsubscribes() -> None:
    async def scenario() -> None:
        notifier, ledger = EventNotifier(), Ledger(1)

        closed = follow(notifier, PROJECT, ledger.read_after, 0, heartbeat=LONG)
        assert await take(anext(closed)) == 1
        assert notifier.subscriber_count(PROJECT) == 1
        await closed.aclose()
        assert notifier.subscriber_count(PROJECT) == 0

        cancelled = follow(notifier, PROJECT, ledger.read_after, 1, heartbeat=LONG)
        waiting = asyncio.ensure_future(anext(cancelled))
        await asyncio.sleep(0.05)
        assert notifier.subscriber_count(PROJECT) == 1
        waiting.cancel()  # what a client disconnect does to the response task
        with suppress(asyncio.CancelledError):
            await waiting
        assert notifier.subscriber_count(PROJECT) == 0

    asyncio.run(scenario())
