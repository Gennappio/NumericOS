from __future__ import annotations

from numericos.persistence.ordering import STEP, place, ranks

COLUMN = ["a", "b", "c"]


def test_append_when_position_is_none() -> None:
    assert place(COLUMN, "x", None) == ["a", "b", "c", "x"]


def test_insert_at_the_front() -> None:
    assert place(COLUMN, "x", 0) == ["x", "a", "b", "c"]


def test_position_beyond_the_end_is_clamped() -> None:
    assert place(COLUMN, "x", 99) == ["a", "b", "c", "x"]


def test_move_inside_the_same_column() -> None:
    assert place(COLUMN, "c", 0) == ["c", "a", "b"]
    assert place(COLUMN, "a", 2) == ["b", "c", "a"]
    assert place(COLUMN, "b", 1) == ["a", "b", "c"]


def test_ranks_step_by_1000() -> None:
    assert ranks(["a", "b", "c"]) == {"a": 0, "b": STEP, "c": 2 * STEP}
