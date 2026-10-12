"""Incremental reads of the append-only JSON Lines files a monitor writes.

A cursor is a byte offset. A read returns only complete lines, so a reader never sees half a
record while the monitor is still writing, and the returned cursor always starts a line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from numericos.core.errors import CursorAheadError, InvalidRequestError

CHUNK = 1024 * 1024
#: A page is also bounded in bytes: a few very long lines must not become a huge response.
PAGE_BYTES = 8 * 1024 * 1024


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def read_after(path: Path, after: int, limit: int) -> tuple[list[dict[str, Any]], int, bool]:
    """Up to ``limit`` records starting at byte ``after`` (fewer if they are very long).

    Returns the records, the cursor after the last one, and whether that is the end of what is
    recorded so far (no further complete record follows). A missing file is an empty one. A
    cursor that this file cannot have produced is refused: one beyond its end, or one that
    does not start a record.
    """
    size = file_size(path)
    if after > size:
        raise CursorAheadError(
            f"cursor {after} is beyond the {size} bytes recorded so far",
            details={"cursor": after, "size": size},
        )
    records: list[dict[str, Any]] = []
    cursor = after
    if size == after:
        return records, cursor, True
    more = False
    with path.open("rb") as handle:
        if after > 0:
            handle.seek(after - 1)
            if handle.read(1) != b"\n":
                raise InvalidRequestError(
                    f"cursor {after} does not start a record",
                    details={
                        "errors": [
                            {
                                "loc": ["query", "after"],
                                "msg": "not a cursor returned by this resource",
                                "type": "invalid_cursor",
                            }
                        ]
                    },
                )
        buffer = b""
        while not more:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            *lines, buffer = (buffer + chunk).split(b"\n")
            for line in lines:
                if len(records) == limit or (records and cursor - after >= PAGE_BYTES):
                    more = True  # a complete record beyond the page: the reader should go on
                    break
                cursor += len(line) + 1
                records.append(json.loads(line))
    return records, cursor, not more


def read_to_end(path: Path, after: int) -> tuple[list[dict[str, Any]], int]:
    """Every complete record after byte ``after``, and the cursor behind the last one."""
    records: list[dict[str, Any]] = []
    cursor, at_end = after, False
    while not at_end:
        page, cursor, at_end = read_after(path, cursor, 5000)
        records.extend(page)
    return records, cursor


def tail_start(path: Path, lines: int) -> int:
    """The byte offset at which the last ``lines`` complete lines of the file begin."""
    size = file_size(path)
    if lines <= 0 or size == 0:
        return size
    with path.open("rb") as handle:
        position = size
        tail = b""
        while position > 0 and tail.count(b"\n") <= lines:
            step = min(CHUNK, position)
            position -= step
            handle.seek(position)
            tail = handle.read(step) + tail
    if tail.count(b"\n") <= lines:
        return 0  # the whole file has no more than the requested lines
    # A complete line ends with a newline: N lines begin after the (N+1)-th newline from the end.
    index = len(tail)
    for _ in range(lines + 1):
        index = tail.rfind(b"\n", 0, index)
    return position + index + 1
