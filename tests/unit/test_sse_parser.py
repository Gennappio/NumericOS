from __future__ import annotations

from numericos.cli.client import iter_sse


def parse(text: str) -> list[tuple[str | None, str]]:
    return list(iter_sse(text.splitlines()))


def test_events_are_dispatched_on_blank_lines_with_their_id() -> None:
    stream = 'id: 7\ndata: {"seq":7}\n\nid: 8\ndata: {"seq":8}\n\n'

    assert parse(stream) == [("7", '{"seq":7}'), ("8", '{"seq":8}')]


def test_comments_and_fields_without_data_are_not_events() -> None:
    stream = "retry: 2000\n\n: ping - 2026-10-12 10:10:09\n\nid: 1\ndata: x\n\n"

    assert parse(stream) == [("1", "x")]


def test_multiline_data_is_joined_and_one_leading_space_is_removed() -> None:
    stream = "id: 3\ndata: first\ndata:  second\ndata:third\n\n"

    assert parse(stream) == [("3", "first\n second\nthird")]


def test_the_event_id_stays_in_effect_until_replaced() -> None:
    stream = "id: 5\ndata: a\n\ndata: b\n\nid: 6\ndata: c\n\n"

    assert parse(stream) == [("5", "a"), ("5", "b"), ("6", "c")]


def test_an_unterminated_event_is_not_dispatched() -> None:
    assert parse("id: 9\ndata: cut off mid-event") == []
