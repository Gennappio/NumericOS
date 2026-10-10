"""CLI contract: parseable JSON on stdout, diagnostics on stderr, documented exit codes."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from numericos import __version__
from numericos.cli.main import EXIT_UNREACHABLE, app
from tests.conftest import LiveServer, free_port

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_health_json_is_parseable_and_stdout_is_clean(live_server: LiveServer) -> None:
    result = runner.invoke(app, ["health", "--json", "--api-url", live_server.base_url])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["db"] == "ok"  # `serve` applied the migrations at startup
    assert result.stderr == ""


def test_health_human_output(live_server: LiveServer) -> None:
    result = runner.invoke(app, ["health", "--api-url", live_server.base_url])

    assert result.exit_code == 0, result.output
    assert f"numericos {__version__} ok at {live_server.base_url}" in result.stdout


def test_unreachable_backend_exits_3_with_empty_stdout() -> None:
    dead_url = f"http://127.0.0.1:{free_port()}"

    result = runner.invoke(app, ["health", "--json", "--api-url", dead_url])

    assert result.exit_code == EXIT_UNREACHABLE
    assert result.stdout == ""
    assert "cannot reach the NumericOS API" in result.stderr


def test_db_upgrade_and_current(tmp_path: Path) -> None:
    data_dir = str(tmp_path / "data")

    before = runner.invoke(app, ["db", "current", "--json", "--data-dir", data_dir])
    upgrade = runner.invoke(app, ["db", "upgrade", "--json", "--data-dir", data_dir])
    after = runner.invoke(app, ["db", "current", "--json", "--data-dir", data_dir])

    assert before.exit_code == 0, before.output
    assert json.loads(before.stdout)["up_to_date"] is False
    assert upgrade.exit_code == 0, upgrade.output
    assert json.loads(upgrade.stdout)["schema_revision"] == "0001"
    assert json.loads(after.stdout) == {
        "db_path": f"{data_dir}/numericos.db",
        "schema_revision": "0001",
        "expected_revision": "0001",
        "up_to_date": True,
    }


def test_openapi_export_is_the_public_contract() -> None:
    result = runner.invoke(app, ["openapi"])

    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["info"]["title"] == "NumericOS API"
    assert "/v1/health" in document["paths"]
    assert "ErrorEnvelope" in document["components"]["schemas"]
