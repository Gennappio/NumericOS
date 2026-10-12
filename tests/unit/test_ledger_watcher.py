"""Commits of other processes are noticed without waiting for the stream heartbeat."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.engine import Engine

from numericos.config import Settings
from numericos.events.notifier import EventNotifier
from numericos.events.watcher import LedgerWatcher
from numericos.persistence.unit_of_work import UnitOfWork
from tests import factories


def commit_event(uow: Callable[[], UnitOfWork]) -> int:
    """Commit a project and its event the way another process would: through its own notifier."""
    with uow() as work:
        project = work.projects.add(factories.project())
        event = work.record(factories.event(project.id, project.id))
        work.commit()
        return event.seq


def test_a_commit_made_elsewhere_wakes_the_subscribers_of_this_process(
    settings: Settings, engine: Engine, uow: Callable[[], UnitOfWork]
) -> None:
    api_notifier = EventNotifier()  # the notifier of "this" process; `uow` has another one
    watcher = LedgerWatcher(settings.db_path, api_notifier, interval=0.05)

    async def scenario() -> int:
        with api_notifier.subscribe("prj_any") as wake:
            await asyncio.sleep(0.2)  # the watcher has seen the ledger as it is
            assert not wake.is_set()
            committed = await asyncio.to_thread(commit_event, uow)
            await asyncio.wait_for(wake.wait(), timeout=2)
            return committed

    watcher.start()
    try:
        seq = asyncio.run(scenario())
    finally:
        watcher.stop()

    assert seq >= 1
    assert api_notifier.announce_foreign(seq) is False  # the head it announced is this one
    assert not watcher.is_alive()


def test_the_watcher_waits_for_a_database_that_does_not_exist_yet(tmp_path: Path) -> None:
    notifier = EventNotifier()
    watcher = LedgerWatcher(tmp_path / "absent" / "numericos.db", notifier, interval=0.02)

    watcher.start()
    threading.Event().wait(0.2)
    alive = watcher.is_alive()
    watcher.stop()

    assert alive  # it keeps looking instead of ending
    assert not watcher.is_alive()
    assert not (tmp_path / "absent").exists()  # and it creates nothing
