"""The Server-Sent Events view of the ledger, against a real server process."""

from __future__ import annotations

import time

import httpx
import pytest

from numericos.core.enums import CardType
from numericos.core.ids import new_id
from numericos.core.schemas import CardCreate
from numericos.events.ledger import EventContext
from numericos.events.notifier import EventNotifier
from numericos.persistence.engine import make_engine, make_session_factory
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services import cards
from tests.conftest import LiveServer
from tests.integration.helpers import (
    EVENT_STREAM,
    Json,
    event_stream,
    ledger,
    new_card,
    new_project,
    take,
)


def seqs(events: list[Json]) -> list[int]:
    return [event["seq"] for event in events]


def test_the_stream_and_the_json_page_are_two_views_of_the_same_ledger(
    live_server: LiveServer,
) -> None:
    project = new_project(live_server)
    new_card(live_server, project["id"], "a")
    new_card(live_server, project["id"], "b")

    with event_stream(live_server, project["id"]) as stream:
        streamed = take(stream, 3)

    assert streamed == ledger(live_server, project["id"])
    assert [event["type"] for event in streamed] == [
        "PROJECT_CREATED",
        "CARD_CREATED",
        "CARD_CREATED",
    ]


def test_reconnecting_with_last_event_id_replays_exactly_what_was_missed(
    live_server: LiveServer,
) -> None:
    project = new_project(live_server)
    new_card(live_server, project["id"], "seen")
    with event_stream(live_server, project["id"]) as stream:
        last_seen = take(stream, 2)[-1]["seq"]

    # While the client is away, two events are committed.
    new_card(live_server, project["id"], "missed 1")
    new_card(live_server, project["id"], "missed 2")

    with event_stream(live_server, project["id"], last_event_id=last_seen) as stream:
        missed = take(stream, 2)
        new_card(live_server, project["id"], "after reconnect")
        following = take(stream, 1)

    titles = [event["payload"]["card"]["title"] for event in missed + following]
    assert titles == ["missed 1", "missed 2", "after reconnect"]  # once each, in order
    assert seqs(missed + following) == sorted(seqs(missed + following))
    assert all(event["seq"] > last_seen for event in missed)
    assert missed + following == ledger(live_server, project["id"])[2:]


def test_the_after_cursor_resumes_the_same_way(live_server: LiveServer) -> None:
    project = new_project(live_server)
    for title in ("a", "b", "c"):
        new_card(live_server, project["id"], title)
    recorded = ledger(live_server, project["id"])

    with event_stream(live_server, project["id"], after=recorded[1]["seq"]) as stream:
        resumed = take(stream, 2)
    with event_stream(
        live_server, project["id"], after=recorded[0]["seq"], last_event_id=recorded[2]["seq"]
    ) as stream:
        later_cursor_wins = take(stream, 1)

    assert resumed == recorded[2:]
    assert later_cursor_wins == recorded[3:]


def test_a_commit_reaches_an_idle_subscriber_at_once(live_server: LiveServer) -> None:
    project = new_project(live_server)
    with event_stream(live_server, project["id"]) as stream:
        take(stream, 1)  # the replay is over: the server now waits for a wake-up

        started = time.monotonic()
        card = new_card(live_server, project["id"], "pushed")
        (pushed,) = take(stream, 1)
        elapsed = time.monotonic() - started

    assert pushed["subject_id"] == card["id"]
    assert elapsed < 2.0, "delivered by the 15 s heartbeat instead of the post-commit wake-up"


def test_events_committed_by_another_process_arrive_within_a_heartbeat(
    fast_heartbeat_server: LiveServer,
) -> None:
    server = fast_heartbeat_server
    project = new_project(server)
    with event_stream(server, project["id"]) as stream:
        take(stream, 1)

        # A second process (what the M3 job supervisor will be) writes to the same database.
        engine = make_engine(server.data_dir / "numericos.db")
        cards.create_card(
            UnitOfWork(make_session_factory(engine), EventNotifier()),
            project["id"],
            CardCreate(type=CardType.EXPERIMENT, title="written by another process"),
            EventContext(actor="worker:test", correlation_id=new_id("cor"), producer="worker"),
        )
        engine.dispose()

        started = time.monotonic()
        (event,) = take(stream, 1)
        elapsed = time.monotonic() - started

    assert event["actor"] == "worker:test"
    assert event["producer"] == "worker"
    assert event["payload"]["card"]["title"] == "written by another process"
    assert elapsed < 5.0


def test_an_unknown_project_is_a_404_before_any_stream_starts(live_server: LiveServer) -> None:
    response = httpx.get(
        f"{live_server.base_url}/v1/events",
        params={"project_id": "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2"},
        headers=EVENT_STREAM,
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_cursor_ahead_of_the_ledger_is_refused_not_silently_starved(
    live_server: LiveServer,
) -> None:
    project = new_project(live_server)
    head = ledger(live_server, project["id"])[-1]["seq"]
    url = f"{live_server.base_url}/v1/events"

    ahead = httpx.get(
        url, params={"project_id": project["id"], "after": head + 1}, headers=EVENT_STREAM
    )
    stale_reconnect = httpx.get(
        url, params={"project_id": project["id"]}, headers={**EVENT_STREAM, "Last-Event-ID": "999"}
    )

    for response in (ahead, stale_reconnect):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CURSOR_AHEAD"
        assert response.json()["error"]["details"]["ledger_head"] == head
    with event_stream(live_server, project["id"], after=head) as stream:  # the head is valid
        new_card(live_server, project["id"], "next")
        assert take(stream, 1)[0]["seq"] == head + 1


@pytest.mark.parametrize(
    ("params", "headers", "location"),
    [
        ({"limit": 5}, {}, ["query", "limit"]),
        ({"before": 9}, {}, ["query", "before"]),
        ({"order": "desc"}, {}, ["query", "order"]),
        ({"run_id": "run_01J9W2Z4K7QX8YB3N5M6T0R1S2"}, {}, ["query", "run_id"]),
        ({}, {"Last-Event-ID": "not-a-seq"}, ["header", "last-event-id"]),
    ],
)
def test_requests_a_stream_cannot_honour_are_rejected(
    live_server: LiveServer,
    params: Json,
    headers: dict[str, str],
    location: list[str],
) -> None:
    project = new_project(live_server)

    response = httpx.get(
        f"{live_server.base_url}/v1/events",
        params={"project_id": project["id"], **params},
        headers={**EVENT_STREAM, **headers},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == location


def test_the_json_page_ignores_nothing_and_keeps_its_default_size(live_server: LiveServer) -> None:
    project = new_project(live_server)

    response = httpx.get(f"{live_server.base_url}/v1/events", params={"project_id": project["id"]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json()["events"] == ledger(live_server, project["id"])


def test_a_server_with_open_subscribers_stops_promptly(live_server: LiveServer) -> None:
    project = new_project(live_server)
    with event_stream(live_server, project["id"]) as stream:
        take(stream, 1)

        started = time.monotonic()
        live_server.stop()
        elapsed = time.monotonic() - started

        assert not live_server.killed, "SIGTERM was ignored while a stream was open"
        assert elapsed < 5.0
        with pytest.raises((httpx.TransportError, StopIteration)):
            next(stream)  # the subscriber learns that the stream is over
