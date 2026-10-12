"""Notice commits made by other processes and wake this process's subscribers.

The supervisor writes run events from its own process. The API learns about them here: SQLite's
``data_version`` changes whenever another connection commits, so one cheap query per interval
tells whether to look at the ledger head. Nothing is delivered from here; subscribers still read
the ledger by cursor. Without this watcher they would catch up one heartbeat later.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from urllib.parse import quote

from numericos.events.notifier import EventNotifier


class LedgerWatcher(threading.Thread):
    def __init__(self, db_path: Path, notifier: EventNotifier, interval: float = 0.25) -> None:
        super().__init__(name="numericos-ledger-watcher", daemon=True)
        self._uri = f"file:{quote(str(db_path))}?mode=ro"
        self._notifier = notifier
        self._interval = interval
        self._stopping = threading.Event()

    def run(self) -> None:
        connection: sqlite3.Connection | None = None
        seen: int | None = None
        while not self._stopping.wait(self._interval):
            try:
                if connection is None:
                    connection = sqlite3.connect(
                        self._uri,
                        uri=True,
                        isolation_level=None,
                        check_same_thread=False,
                        timeout=1,
                    )
                version = connection.execute("PRAGMA data_version").fetchone()[0]
                if version != seen:
                    seen = version
                    head = connection.execute("SELECT max(seq) FROM events").fetchone()[0]
                    self._notifier.announce_foreign(head or 0)
            except sqlite3.Error:
                # No database yet, or not migrated: look again later. Subscribers lose nothing,
                # they still re-read the ledger at every heartbeat.
                if connection is not None:
                    connection.close()
                connection, seen = None, None
        if connection is not None:
            connection.close()

    def stop(self) -> None:
        self._stopping.set()
        self.join(timeout=5)
