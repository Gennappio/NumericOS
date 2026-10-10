"""``numericos`` command line.

Data commands talk to the NumericOS API over HTTP (never to the database directly); the only
server-side commands are ``serve`` and ``db``. Machine mode (``--json``) prints exactly one JSON
document on stdout; diagnostics go to stderr.
Exit codes: 0 success, 1 API error, 2 usage error, 3 API unreachable.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
from sqlalchemy.engine import Engine

from numericos import __version__
from numericos.api.app import create_app
from numericos.cli.client import ApiClient, ApiError, ApiUnreachable
from numericos.config import Settings
from numericos.persistence import migrate as migrations
from numericos.persistence.engine import make_engine

EXIT_API_ERROR = 1
EXIT_UNREACHABLE = 3

app = typer.Typer(
    name="numericos",
    help="NumericOS: agentic workbench for computational research.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
db = typer.Typer(help="Local database administration (server side).", no_args_is_help=True)
app.add_typer(db, name="db")

JsonFlag = Annotated[
    bool, typer.Option("--json", help="Print one JSON document on stdout; diagnostics on stderr.")
]
ApiUrlOption = Annotated[
    str | None,
    typer.Option("--api-url", envvar="NUMERICOS_API_URL", help="Base URL of the NumericOS API."),
]
DataDirOption = Annotated[
    Path | None, typer.Option("--data-dir", help="Directory for the database and artifacts.")
]


def _call[T](as_json: bool, fn: Callable[[], T]) -> T:
    """Run an API call and translate client errors into the documented exit codes."""
    try:
        return fn()
    except ApiUnreachable as exc:
        typer.echo(f"error: cannot reach the NumericOS API at {exc.url} ({exc.cause})", err=True)
        raise typer.Exit(EXIT_UNREACHABLE) from exc
    except ApiError as exc:
        if as_json:
            typer.echo(json.dumps(exc.envelope, sort_keys=True), err=True)
        else:
            typer.echo(f"error [{exc.code}] (HTTP {exc.status_code}): {exc.message}", err=True)
        raise typer.Exit(EXIT_API_ERROR) from exc


def _emit(data: Any, as_json: bool, human: Callable[[Any], str]) -> None:
    typer.echo(json.dumps(data, indent=2, sort_keys=True) if as_json else human(data))


def _local_engine(data_dir: Path | None) -> tuple[Settings, Engine]:
    settings = Settings(data_dir=data_dir) if data_dir is not None else Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings, make_engine(settings.db_path)


@app.command()
def version() -> None:
    """Print the NumericOS version."""
    typer.echo(__version__)


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Bind address (default 127.0.0.1).")] = None,
    port: Annotated[int | None, typer.Option(help="TCP port (default 8765).")] = None,
    data_dir: DataDirOption = None,
    ephemeral: Annotated[
        bool, typer.Option("--ephemeral", help="Fresh temporary data directory (demos, e2e).")
    ] = False,
    migrate: Annotated[
        bool, typer.Option("--migrate/--no-migrate", help="Apply schema migrations at startup.")
    ] = True,
    reload: Annotated[
        bool, typer.Option("--reload", help="Reload on source changes (development only).")
    ] = False,
) -> None:
    """Start the NumericOS API server (loopback-bound by default)."""
    overrides: dict[str, Any] = {
        key: value
        for key, value in {"host": host, "port": port, "data_dir": data_dir}.items()
        if value is not None
    }
    if ephemeral:
        overrides["data_dir"] = Path(tempfile.mkdtemp(prefix="numericos-"))
    settings = Settings(**overrides)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if migrate:
        engine = make_engine(settings.db_path)
        migrations.upgrade(engine)
        engine.dispose()
        typer.echo(f"database {settings.db_path} at schema {migrations.head_revision()}", err=True)
    typer.echo(
        f"NumericOS API {__version__} listening on http://{settings.host}:{settings.port} "
        f"(data_dir={settings.data_dir})",
        err=True,
    )
    if reload:
        os.environ.update(
            {
                "NUMERICOS_HOST": settings.host,
                "NUMERICOS_PORT": str(settings.port),
                "NUMERICOS_DATA_DIR": str(settings.data_dir),
            }
        )
        uvicorn.run(
            "numericos.api.app:create_app_from_env",
            factory=True,
            reload=True,
            host=settings.host,
            port=settings.port,
        )
        return
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


@db.command("upgrade")
def db_upgrade(data_dir: DataDirOption = None, json_: JsonFlag = False) -> None:
    """Apply pending schema migrations to the local database."""
    settings, engine = _local_engine(data_dir)
    migrations.upgrade(engine)
    data = {
        "db_path": str(settings.db_path),
        "schema_revision": migrations.current_revision(engine),
    }
    engine.dispose()
    _emit(data, json_, lambda d: f"{d['db_path']} at schema revision {d['schema_revision']}")


@db.command("current")
def db_current(data_dir: DataDirOption = None, json_: JsonFlag = False) -> None:
    """Show the current and the expected schema revision of the local database."""
    settings, engine = _local_engine(data_dir)
    current = migrations.current_revision(engine)
    engine.dispose()
    expected = migrations.head_revision()
    data = {
        "db_path": str(settings.db_path),
        "schema_revision": current,
        "expected_revision": expected,
        "up_to_date": current == expected,
    }
    _emit(
        data,
        json_,
        lambda d: (
            f"{d['db_path']}: schema {d['schema_revision']} (expected {d['expected_revision']})"
        ),
    )


@app.command()
def health(json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """Check that the API is reachable and report its version and database state."""
    with ApiClient(api_url or Settings().api_url) as client:
        data = _call(json_, lambda: client.get("/v1/health"))
    _emit(
        data,
        json_,
        lambda d: (
            f"{d['app']} {d['version']} {d['status']} at {client.base_url} "
            f"(db {d['db']}, schema {d['schema_revision']})"
        ),
    )


@app.command()
def openapi(
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write here instead of stdout.")
    ] = None,
) -> None:
    """Export the OpenAPI document of the public API (developer utility, no server needed)."""
    document = create_app(Settings()).openapi()
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(text, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    typer.echo(f"wrote {output}", err=True)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
