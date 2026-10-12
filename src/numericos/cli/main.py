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
from numericos.cli import seed
from numericos.cli.client import ApiClient, ApiError, ApiUnreachable
from numericos.config import Settings
from numericos.core.enums import CardType, WorkflowStatus
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
project = typer.Typer(help="Research projects.", no_args_is_help=True)
card = typer.Typer(help="Typed cards on a project's scientific board.", no_args_is_help=True)
events = typer.Typer(help="A project's ordered event ledger.", no_args_is_help=True)
app.add_typer(db, name="db")
app.add_typer(project, name="project")
app.add_typer(card, name="card")
app.add_typer(events, name="events")

Record = dict[str, Any]

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
ProjectOption = Annotated[str, typer.Option("--project", "-p", help="Project ID.")]
VersionOption = Annotated[
    int | None,
    typer.Option(
        "--version",
        min=1,
        help="Version you expect the record to have; default: its latest (last write wins).",
    ),
]


# --------------------------------------------------------------------------- plumbing


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


def _api[T](
    as_json: bool,
    api_url: str | None,
    fn: Callable[[ApiClient], T],
    *,
    actor: str = "cli:local",
) -> T:
    with ApiClient(api_url or Settings().api_url, actor=actor) as client:
        return _call(as_json, lambda: fn(client))


def _emit(data: Any, as_json: bool, human: Callable[[Any], str]) -> None:
    typer.echo(json.dumps(data, indent=2, sort_keys=True) if as_json else human(data))


def _given(**fields: Any) -> Record:
    """The options the user actually passed."""
    return {name: value for name, value in fields.items() if value is not None}


def _require_change(fields: Record, options: str) -> None:
    if not fields:
        raise typer.BadParameter(f"nothing to change: pass at least one of {options}")


def _patch(client: ApiClient, path: str, version: int | None, fields: Record) -> Record:
    """PATCH with optimistic locking; without ``--version`` the latest version is used."""
    current = version if version is not None else int(client.get(path)["version"])
    result: Record = client.patch(path, {"version": current, **fields})
    return result


def _local_engine(data_dir: Path | None) -> tuple[Settings, Engine]:
    settings = Settings(data_dir=data_dir) if data_dir is not None else Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings, make_engine(settings.db_path)


# --------------------------------------------------------------------------- human output


def _demo_tag(record: Record) -> str:
    return "  [demo]" if record["is_demo"] else ""


def _project_line(record: Record) -> str:
    return f"{record['id']}  v{record['version']}  {record['name']}{_demo_tag(record)}"


def _project_detail(record: Record) -> str:
    return "\n".join(
        [
            f"{record['name']}{_demo_tag(record)}",
            f"  id:                {record['id']} (version {record['version']})",
            f"  research question: {record['research_question'] or '-'}",
            f"  reference:         {record['root_path'] or '-'}",
            f"  updated:           {record['updated_at']}",
        ]
    )


def _card_line(record: Record) -> str:
    return f"{record['id']}  v{record['version']}  [{record['type']}] {record['title']}"


def _card_detail(record: Record) -> str:
    lines = [
        _card_line(record),
        f"  project: {record['project_id']}",
        f"  status:  {record['workflow_status']} (rank {record['sort_order']})",
    ]
    if record["description"]:
        lines.append(f"  {record['description']}")
    return "\n".join(lines)


def _board_text(board: Record) -> str:
    lines: list[str] = []
    for status in board["workflow_statuses"]:
        column = [item for item in board["cards"] if item["workflow_status"] == status]
        lines.append(f"{status} ({len(column)})")
        lines.extend(f"  {_card_line(item)}" for item in column)
    return "\n".join(lines)


def _event_line(record: Record) -> str:
    return (
        f"{record['seq']:>6}  {record['timestamp_utc']}  {record['type']:<16}  "
        f"{record['subject_id']}  {record['actor']}"
    )


# --------------------------------------------------------------------------- server side


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
        bool,
        typer.Option(
            "--reload",
            help="Restart on source changes (development). Migrations run once, at startup.",
        ),
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
            reload_dirs=[str(Path(__file__).resolve().parents[1])],  # the numericos package
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


# --------------------------------------------------------------------------- API client commands


@app.command()
def health(json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """Check that the API is reachable and report its version and database state."""
    base_url = api_url or Settings().api_url
    data = _api(json_, base_url, lambda client: client.get("/v1/health"))
    _emit(
        data,
        json_,
        lambda d: (
            f"{d['app']} {d['version']} {d['status']} at {base_url.rstrip('/')} "
            f"(db {d['db']}, schema {d['schema_revision']})"
        ),
    )


@app.command("seed-demo")
def seed_demo(json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """Create one clearly marked demo project. Idempotent; demo data is never created implicitly."""
    data = _api(json_, api_url, seed.seed_demo, actor="cli:seed")
    _emit(
        data,
        json_,
        lambda d: (
            f"{'created' if d['created'] else 'already present'}: "
            f"{_project_line(d['project'])} ({d['card_count']} cards)"
        ),
    )


@project.command("list")
def project_list(json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """List projects in creation order."""
    data = _api(json_, api_url, lambda client: client.get("/v1/projects"))
    _emit(
        data,
        json_,
        lambda d: "\n".join(_project_line(item) for item in d["projects"]) or "no projects yet",
    )


@project.command("add")
def project_add(
    name: Annotated[str, typer.Argument(help="Project name.")],
    question: Annotated[str, typer.Option("--question", "-q", help="Research question.")] = "",
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    root_path: Annotated[
        str | None,
        typer.Option("--root-path", help="Absolute path of the research code (reference only)."),
    ] = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Create a research project."""
    body = {
        "name": name,
        "research_question": question,
        "description": description,
        "root_path": root_path,
    }
    data = _api(json_, api_url, lambda client: client.post("/v1/projects", body))
    _emit(data, json_, _project_detail)


@project.command("show")
def project_show(
    project_id: Annotated[str, typer.Argument(metavar="PROJECT_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show one project."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/projects/{project_id}"))
    _emit(data, json_, _project_detail)


@project.command("update")
def project_update(
    project_id: Annotated[str, typer.Argument(metavar="PROJECT_ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    question: Annotated[str | None, typer.Option("--question", "-q")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    root_path: Annotated[str | None, typer.Option("--root-path")] = None,
    version: VersionOption = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Change a project's name, research question, description or reference path."""
    fields = _given(
        name=name, research_question=question, description=description, root_path=root_path
    )
    _require_change(fields, "--name, --question, --description, --root-path")
    path = f"/v1/projects/{project_id}"
    data = _api(json_, api_url, lambda client: _patch(client, path, version, fields))
    _emit(data, json_, _project_detail)


@card.command("add")
def card_add(
    project_id: ProjectOption,
    card_type: Annotated[CardType, typer.Option("--type", "-t", help="Kind of card.")],
    title: Annotated[str, typer.Option("--title", help="Card title.")],
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    status: Annotated[
        WorkflowStatus, typer.Option("--status", "-s", help="Workflow column.")
    ] = WorkflowStatus.BACKLOG,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Add a typed card at the end of a workflow column."""
    body = {
        "type": card_type.value,
        "title": title,
        "description": description,
        "workflow_status": status.value,
    }
    data = _api(
        json_, api_url, lambda client: client.post(f"/v1/projects/{project_id}/cards", body)
    )
    _emit(data, json_, _card_detail)


@card.command("list")
def card_list(
    project_id: ProjectOption, json_: JsonFlag = False, api_url: ApiUrlOption = None
) -> None:
    """Show a project's board: cards by workflow column, in rank order."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/projects/{project_id}/board"))
    _emit(data, json_, _board_text)


@card.command("show")
def card_show(
    card_id: Annotated[str, typer.Argument(metavar="CARD_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show one card."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/cards/{card_id}"))
    _emit(data, json_, _card_detail)


@card.command("move")
def card_move(
    card_id: Annotated[str, typer.Argument(metavar="CARD_ID")],
    status: Annotated[
        WorkflowStatus | None, typer.Option("--status", "-s", help="Destination column.")
    ] = None,
    position: Annotated[
        int | None,
        typer.Option(
            "--position",
            min=0,
            help="Zero-based index in the column; omitted appends when the column changes.",
        ),
    ] = None,
    version: VersionOption = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Move a card to another column and/or to another position in its column."""
    fields = _given(workflow_status=status.value if status else None, position=position)
    _require_change(fields, "--status, --position")
    path = f"/v1/cards/{card_id}"
    data = _api(json_, api_url, lambda client: _patch(client, path, version, fields))
    _emit(data, json_, _card_detail)


@card.command("update")
def card_update(
    card_id: Annotated[str, typer.Argument(metavar="CARD_ID")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    card_type: Annotated[CardType | None, typer.Option("--type", "-t")] = None,
    version: VersionOption = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Change a card's title, description or type."""
    fields = _given(
        title=title, description=description, type=card_type.value if card_type else None
    )
    _require_change(fields, "--title, --description, --type")
    path = f"/v1/cards/{card_id}"
    data = _api(json_, api_url, lambda client: _patch(client, path, version, fields))
    _emit(data, json_, _card_detail)


@events.command("list")
def events_list(
    project_id: ProjectOption,
    after: Annotated[
        int | None,
        typer.Option("--after", min=0, help="Cursor: only events with seq greater than this."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
    newest_first: Annotated[bool, typer.Option("--desc", help="Newest first.")] = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Read a project's ledger in sequence order (the same events the GUI replays)."""
    params = _given(
        project_id=project_id, after=after, limit=limit, order="desc" if newest_first else "asc"
    )
    data = _api(json_, api_url, lambda client: client.get("/v1/events", params))
    _emit(
        data, json_, lambda d: "\n".join(_event_line(item) for item in d["events"]) or "no events"
    )
    if data["has_more"] and not json_ and not newest_first:
        typer.echo(f"more events available: --after {data['next_cursor']}", err=True)


@events.command("follow")
def events_follow(
    project_id: ProjectOption,
    after: Annotated[
        int,
        typer.Option("--after", min=0, help="Resume after this seq (default: from the start)."),
    ] = 0,
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Stop after this many events.")
    ] = None,
    json_: Annotated[
        bool, typer.Option("--json", help="One JSON document per line (JSON Lines) on stdout.")
    ] = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Replay a project's ledger from a cursor, then print events as they are committed.

    Stop it with Ctrl+C. If the stream breaks, the command says after which seq, so that
    `--after` resumes exactly there, and exits with code 3.
    """
    cursor = after
    printed = 0
    with ApiClient(api_url or Settings().api_url) as client:
        try:
            for event in client.follow_events(project_id, after):
                typer.echo(json.dumps(event, sort_keys=True) if json_ else _event_line(event))
                cursor = event["seq"]
                printed += 1
                if limit is not None and printed >= limit:
                    return
        except KeyboardInterrupt:
            return
        except ApiError as exc:
            if json_:
                typer.echo(json.dumps(exc.envelope, sort_keys=True), err=True)
            else:
                typer.echo(f"error [{exc.code}] (HTTP {exc.status_code}): {exc.message}", err=True)
            raise typer.Exit(EXIT_API_ERROR) from exc
        except ApiUnreachable as exc:
            typer.echo(
                f"error: lost the event stream of {exc.url} ({exc.cause}); "
                f"last seq {cursor}, resume with --after {cursor}",
                err=True,
            )
            raise typer.Exit(EXIT_UNREACHABLE) from exc
    typer.echo(
        f"error: the server closed the event stream; last seq {cursor}, "
        f"resume with --after {cursor}",
        err=True,
    )
    raise typer.Exit(EXIT_UNREACHABLE)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
