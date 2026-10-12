"""Incremental reads of the files a monitor appends to."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from numericos.core.errors import CursorAheadError, InvalidRequestError
from numericos.observability import files


def lines(*values: int) -> bytes:
    return b"".join(json.dumps({"n": value}).encode() + b"\n" for value in values)


def numbers(records: list[dict[str, int]]) -> list[int]:
    return [record["n"] for record in records]


def test_a_reading_continues_exactly_where_the_previous_one_stopped(tmp_path: Path) -> None:
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(1, 2, 3, 4, 5))

    first, cursor, at_end = files.read_after(path, 0, 2)
    second, cursor_2, at_end_2 = files.read_after(path, cursor, 2)
    third, cursor_3, at_end_3 = files.read_after(path, cursor_2, 2)
    nothing, cursor_4, at_end_4 = files.read_after(path, cursor_3, 2)

    assert (numbers(first), at_end) == ([1, 2], False)
    assert (numbers(second), at_end_2) == ([3, 4], False)
    assert (numbers(third), at_end_3) == ([5], True)
    assert (nothing, cursor_4, at_end_4) == ([], cursor_3, True)
    assert cursor_3 == path.stat().st_size


def test_a_page_that_ends_with_the_last_record_is_the_end(tmp_path: Path) -> None:
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(1, 2))

    records, cursor, at_end = files.read_after(path, 0, 2)

    assert (numbers(records), cursor, at_end) == ([1, 2], path.stat().st_size, True)


def test_a_line_that_is_still_being_written_is_not_returned(tmp_path: Path) -> None:
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(1) + b'{"n": 2')

    records, cursor, at_end = files.read_after(path, 0, 10)
    with path.open("ab") as handle:
        handle.write(b"}\n")
    later, _cursor, _at_end = files.read_after(path, cursor, 10)

    assert (numbers(records), at_end) == ([1], True)  # nothing complete follows yet
    assert cursor == len(lines(1))
    assert numbers(later) == [2]


def test_records_longer_than_one_read_are_put_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "CHUNK", 7)
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(1000000, 2, 3000000))

    records, cursor, at_end = files.read_after(path, 0, 10)

    assert (numbers(records), cursor, at_end) == ([1000000, 2, 3000000], path.stat().st_size, True)


def test_a_missing_file_is_an_empty_one(tmp_path: Path) -> None:
    assert files.read_after(tmp_path / "absent.jsonl", 0, 10) == ([], 0, True)
    assert files.tail_start(tmp_path / "absent.jsonl", 5) == 0


def test_a_cursor_this_file_cannot_have_produced_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(1, 2))

    with pytest.raises(CursorAheadError):
        files.read_after(path, path.stat().st_size + 1, 10)
    with pytest.raises(InvalidRequestError, match="does not start a record"):
        files.read_after(path, 3, 10)


@pytest.mark.parametrize(
    ("content", "count", "expected"),
    [
        (lines(1, 2, 3, 4), 2, [3, 4]),
        (lines(1, 2, 3, 4), 4, [1, 2, 3, 4]),
        (lines(1, 2, 3, 4), 9, [1, 2, 3, 4]),
        (lines(1, 2, 3) + b'{"n": 4', 2, [2, 3]),  # the unfinished line does not count
        (b"", 3, []),
    ],
)
def test_the_tail_starts_at_the_last_complete_lines(
    tmp_path: Path, content: bytes, count: int, expected: list[int]
) -> None:
    path = tmp_path / "output.jsonl"
    path.write_bytes(content)

    records, _cursor, _at_end = files.read_after(path, files.tail_start(path, count), 100)

    assert numbers(records) == expected


def test_the_tail_is_found_without_reading_the_whole_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "CHUNK", 16)
    path = tmp_path / "output.jsonl"
    path.write_bytes(lines(*range(200)))

    records, _cursor, _at_end = files.read_after(path, files.tail_start(path, 3), 100)

    assert numbers(records) == [197, 198, 199]


def test_a_long_series_is_counted_and_streamed_without_its_unfinished_last_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "CHUNK", 16)
    path = tmp_path / "residual.jsonl"
    path.write_bytes(lines(*range(100)) + b'{"n": 10')

    count, end = files.complete_extent(path)
    streamed = [record["n"] for record in files.iter_records(path, end)]

    assert (count, end) == (100, len(lines(*range(100))))
    assert streamed == list(range(100))
    assert files.complete_extent(tmp_path / "absent.jsonl") == (0, 0)
    assert list(files.iter_records(tmp_path / "absent.jsonl", 0)) == []
