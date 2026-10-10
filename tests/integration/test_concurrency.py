"""Concurrent writers against a real server process: ordering and optimistic locking hold."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from tests.conftest import LiveServer

Json = dict[str, Any]
WRITERS = 20


def test_concurrent_moves_leave_a_consistent_column(live_server: LiveServer) -> None:
    with httpx.Client(base_url=live_server.base_url, timeout=30) as http:
        project = http.post("/v1/projects", json={"name": "concurrency"}).json()
        cards: list[Json] = [
            http.post(
                f"/v1/projects/{project['id']}/cards", json={"type": "task", "title": f"card {i}"}
            ).json()
            for i in range(WRITERS)
        ]

    def move_to_front_of_active(card: Json) -> int:
        response = httpx.patch(
            f"{live_server.base_url}/v1/cards/{card['id']}",
            json={"version": card["version"], "workflow_status": "active", "position": 0},
            timeout=30,
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        statuses = list(pool.map(move_to_front_of_active, cards))

    assert statuses == [200] * WRITERS, live_server.logs()
    with httpx.Client(base_url=live_server.base_url, timeout=30) as http:
        board = http.get(f"/v1/projects/{project['id']}/board").json()
        ledger = http.get("/v1/events", params={"project_id": project["id"], "limit": 1000}).json()[
            "events"
        ]

    assert {card["workflow_status"] for card in board["cards"]} == {"active"}
    assert {card["id"] for card in board["cards"]} == {card["id"] for card in cards}
    assert [card["sort_order"] for card in board["cards"]] == [i * 1000 for i in range(WRITERS)]
    moves = [event for event in ledger if event["type"] == "CARD_MOVED"]
    assert len(moves) == WRITERS
    seqs = [event["seq"] for event in ledger]
    assert seqs == sorted(set(seqs))


def test_concurrent_edits_of_one_card_let_exactly_one_writer_win(live_server: LiveServer) -> None:
    with httpx.Client(base_url=live_server.base_url, timeout=30) as http:
        project = http.post("/v1/projects", json={"name": "contention"}).json()
        card = http.post(
            f"/v1/projects/{project['id']}/cards", json={"type": "task", "title": "contested"}
        ).json()

    def rename(writer: int) -> tuple[int, str]:
        response = httpx.patch(
            f"{live_server.base_url}/v1/cards/{card['id']}",
            json={"version": 1, "title": f"writer {writer}"},
            timeout=30,
        )
        code = "" if response.is_success else response.json()["error"]["code"]
        return response.status_code, code

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        outcomes = list(pool.map(rename, range(WRITERS)))

    assert sorted(outcomes) == [(200, "")] + [(409, "STALE_REVISION")] * (WRITERS - 1)
    with httpx.Client(base_url=live_server.base_url, timeout=30) as http:
        stored = http.get(f"/v1/cards/{card['id']}").json()
        ledger = http.get("/v1/events", params={"project_id": project["id"]}).json()["events"]
    assert stored["version"] == 2
    assert stored["title"].startswith("writer ")
    assert [event["type"] for event in ledger].count("CARD_UPDATED") == 1
