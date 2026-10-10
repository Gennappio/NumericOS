"""The committed contract is the application's contract (run `make openapi` after API changes)."""

from __future__ import annotations

import json
from pathlib import Path

from numericos.api.app import create_app
from numericos.config import Settings

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.v1.json"


def test_committed_contract_matches_the_application(settings: Settings) -> None:
    current = json.loads(json.dumps(create_app(settings).openapi()))

    assert current == json.loads(CONTRACT.read_text()), "stale contract: run `make openapi`"


def test_operations_have_stable_readable_ids(settings: Settings) -> None:
    paths = create_app(settings).openapi()["paths"]

    operation_ids = {
        operation["operationId"] for methods in paths.values() for operation in methods.values()
    }
    assert operation_ids == {
        "health",
        "create_project",
        "list_projects",
        "get_project",
        "update_project",
        "get_board",
        "create_card",
        "get_card",
        "update_card",
        "list_events",
    }
