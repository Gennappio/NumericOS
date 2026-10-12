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
        "create_hypothesis",
        "list_hypotheses",
        "get_hypothesis",
        "update_hypothesis",
        "create_experiment",
        "list_experiments",
        "get_experiment",
        "update_experiment",
        "create_run",
        "list_runs",
        "get_run",
        "export_run_record",
        "rerun",
        "trust_execution",
        "revoke_execution_trust",
        "list_project_runs",
        "cancel_run",
        "read_logs",
        "read_resources",
        "list_run_events",
        "list_artifacts",
        "download_artifact",
        "list_workers",
    }
