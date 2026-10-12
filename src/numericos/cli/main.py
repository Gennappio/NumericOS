"""``numericos`` command line.

Data commands talk to the NumericOS API over HTTP (never to the database directly); the only
server-side commands are ``serve``, ``db`` and ``worker run``. Machine mode (``--json``) prints
exactly one JSON document on stdout; diagnostics go to stderr.
Exit codes: 0 success, 1 API error, 2 usage error, 3 API unreachable. A command that waits for a
run (``run watch``, ``run submit --watch``) ends with how the run ended: 0 succeeded, 10 failed,
11 cancelled, 12 timed out, 13 lost, 14 not finished when ``--timeout`` expired.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
import yaml
from sqlalchemy.engine import Engine
from watchfiles import PythonFilter, run_process

from numericos import __version__
from numericos.api.app import create_app
from numericos.cli import seed
from numericos.cli.client import ApiClient, ApiError, ApiUnreachable
from numericos.config import Settings
from numericos.core.enums import CardType, WorkflowStatus
from numericos.executor.worker import Worker
from numericos.persistence import migrate as migrations
from numericos.persistence.engine import make_engine

EXIT_API_ERROR = 1
EXIT_UNREACHABLE = 3
#: How a watched run ended, as the exit code of the command that waited for it.
RUN_EXIT_CODES = {"succeeded": 0, "failed": 10, "cancelled": 11, "timed_out": 12, "lost": 13}
EXIT_STILL_RUNNING = 14
EXIT_INTERRUPTED = 130

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
hypothesis = typer.Typer(help="Falsifiable claims of a project.", no_args_is_help=True)
experiment = typer.Typer(help="Experiments: protocols that runs execute.", no_args_is_help=True)
run = typer.Typer(help="Runs: concrete executions of an experiment.", no_args_is_help=True)
artifact = typer.Typer(help="Files that runs left behind.", no_args_is_help=True)
worker = typer.Typer(
    help="Supervisors: the processes that execute queued runs.", no_args_is_help=True
)
app.add_typer(db, name="db")
app.add_typer(project, name="project")
app.add_typer(card, name="card")
app.add_typer(hypothesis, name="hypothesis")
app.add_typer(experiment, name="experiment")
app.add_typer(run, name="run")
app.add_typer(artifact, name="artifact")
app.add_typer(worker, name="worker")
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
RunArgument = Annotated[str, typer.Argument(metavar="RUN_ID")]
TimeoutOption = Annotated[
    float | None,
    typer.Option("--timeout", min=0, help="Stop waiting after this many seconds (exit code 14)."),
]
QuietFlag = Annotated[
    bool, typer.Option("--quiet", "-q", help="Do not print the program's output while waiting.")
]


class LogStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"
    BUILD = "build"


class StillRunning(Exception):
    """A watched run had not ended when the timeout expired."""


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


def _trust_text(record: Record) -> str:
    trusted_at = record.get("execution_trusted_at")
    return f"trusted since {trusted_at}" if trusted_at else "not trusted (no run can be queued)"


def _project_line(record: Record) -> str:
    return f"{record['id']}  v{record['version']}  {record['name']}{_demo_tag(record)}"


def _project_detail(record: Record) -> str:
    return "\n".join(
        [
            f"{record['name']}{_demo_tag(record)}",
            f"  id:                {record['id']} (version {record['version']})",
            f"  research question: {record['research_question'] or '-'}",
            f"  reference:         {record['root_path'] or '-'}",
            f"  execution:         {_trust_text(record)}",
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


def _hypothesis_line(record: Record) -> str:
    return f"{record['id']}  v{record['version']}  [{record['epistemic_status']}] {record['title']}"


def _hypothesis_detail(record: Record) -> str:
    lines = [
        _hypothesis_line(record),
        f"  claim:      {record['claim']}",
        f"  prediction: {record['prediction'] or '-'}",
    ]
    lines.extend(f"  falsified by: {item}" for item in record["falsification"])
    return "\n".join(lines)


def _experiment_line(record: Record) -> str:
    return (
        f"{record['id']}  v{record['version']}  {record['name']}  "
        f"({record['run_count']} runs, protocol {record['protocol_digest'][:12]})"
    )


def _experiment_detail(record: Record) -> str:
    protocol = record["protocol"]
    variables = ", ".join(
        f"{name} in {values}" for name, values in protocol["independent_variables"].items()
    )
    return "\n".join(
        [
            _experiment_line(record),
            f"  question:   {protocol['question']}",
            f"  hypothesis: {record['hypothesis_id'] or '-'}",
            f"  varies:     {variables or '-'}",
            f"  controls:   {protocol['controls'] or '-'}",
            f"  command:    {' '.join(protocol['execution']['command'])}",
            f"  limits:     {protocol['limits']}",
        ]
    )


def _run_line(record: Record) -> str:
    label = f"  {record['label']}" if record["label"] else ""
    return f"{record['id']}  {record['status']:<10}{label}  {record['parameters']}"


def _run_detail(record: Record) -> str:
    lines = [
        _run_line(record),
        f"  experiment: {record['experiment_id']} (protocol {record['protocol_digest'][:12]})",
        f"  argv:       {record['argv']}",
    ]
    if record["seed"] is not None:
        lines.append(f"  seed:       {record['seed']}")
    if record["failure_class"]:
        lines.append(f"  failure:    {record['failure_class']}")
    if record["status_reason"]:
        lines.append(f"  reason:     {record['status_reason']}")
    lines.append(f"  code:       {_code_text(record['code'])}")
    if record["reproduces_run_id"]:
        lines.append(f"  reproduces: {record['reproduces_run_id']}")
    if record["started_at"]:
        lines.append(f"  ran:        {record['started_at']} -> {record['finished_at'] or '...'}")
    outcome = record["outcome"]
    if record["wall_seconds"] is not None:
        alone = outcome["program_seconds"] if outcome else None
        # Worth saying only when build commands or tidying up took a noticeable part.
        apart = alone is not None and record["wall_seconds"] - alone >= 0.05
        lines.append(
            f"  ended:      {_ending(record)} after {record['wall_seconds']} s"
            + (f"; the program itself ran {alone:.3f} s" if apart else "")
        )
    if outcome and outcome["rusage"]:
        usage = outcome["rusage"]
        lines.append(
            f"  measured:   {usage['cpu_user_seconds']:.3f} s user and "
            f"{usage['cpu_system_seconds']:.3f} s system CPU, largest process "
            f"{_size(usage['max_rss_bytes'])} (the program, from the system at its exit)"
        )
    resources = record["resources"]
    if resources and resources["samples"]:
        lines.append(
            f"  sampled:    at most {_size(resources['max_rss_bytes'])} over the process tree "
            f"in {resources['samples']} samples"
        )
    elif record["finished_at"] and record["started_at"]:
        lines.append("  sampled:    nothing: the program ended before the first sample")
    if record["cancel_requested_at"] and record["finished_at"] is None:
        lines.append(f"  cancel:     requested at {record['cancel_requested_at']}")
    return "\n".join(lines)


def _ending(record: Record) -> str:
    if record["exit_signal"]:
        return f"signal {record['exit_signal']}"
    if record["exit_code"] is None:
        return "no exit code"
    return f"exit code {record['exit_code']}"


def _size(count: int | None) -> str:
    if count is None:
        return "-"
    value = float(count)
    for unit in ("B", "KiB", "MiB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def _clock(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%H:%M:%S.%f")[:-3]


STREAM_MARKS = {"stdout": "out", "stderr": "err", "build": "bld"}


def _log_text(line: Record) -> str:
    """A recorded output line: arrival time (UTC), stream, text."""
    return f"{_clock(line['t'])} {STREAM_MARKS[line['stream']]} | {line['text']}"


def _sample_line(record: Record) -> str:
    return (
        f"{record['elapsed']:>9.1f} s  {record['phase']:<7}  cpu {record['cpu_percent']:>6.1f}%  "
        f"rss {_size(record['rss_bytes']):>10}  "
        f"{record['processes']} proc  {record['threads']} thr"
    )


def _artifact_line(record: Record) -> str:
    digest = record["sha256"][:12] if record["sha256"] else "-"
    return (
        f"{record['id']}  {record['kind']:<17}  {_size(record['size_bytes']):>10}  "
        f"{digest:<12}  {record['name']}"
    )


def _worker_line(record: Record) -> str:
    state = "alive" if record["alive"] else ("stopped" if record["stopped_at"] else "silent")
    return (
        f"{record['id']}  {state:<7}  pid {record['pid']} on {record['hostname']}  "
        f"{record['active_runs']}/{record['max_parallel_runs']} runs  "
        f"heartbeat {record['heartbeat_at']}"
    )


def _code_text(code: Record | None) -> str:
    if code is None:
        return "not recorded"
    if code["mode"] == "ref":
        subject = code["commit"]["subject"] if code["commit"] else ""
        return f"commit {code['sha']} ({code['requested_ref']}) {subject}".rstrip()
    if code["sha"] is None and code["dirty"] is None:
        return "working tree, captured when the run starts"
    state = "with uncommitted changes" if code["dirty"] else "clean"
    return f"working tree at {code['sha']}, {state}"


def _experiment_body(file: Path, name: str | None, hypothesis_id: str | None) -> Record:
    """The request that registers the experiment of a contract file.

    The file is a numericos.experiment.v1 protocol that may also carry 'name' and
    'hypothesis_id'; without a name the experiment is called like the file.
    """
    protocol = _load_mapping(file)
    in_file = {key: protocol.pop(key, None) for key in ("name", "hypothesis_id")}
    return {
        "name": name or in_file["name"] or file.stem,
        "hypothesis_id": hypothesis_id or in_file["hypothesis_id"],
        "protocol": protocol,
    }


def _load_mapping(path: Path) -> Record:
    """A YAML (or JSON) document that must be a mapping."""
    try:
        document = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise typer.BadParameter(f"cannot read {path}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise typer.BadParameter(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise typer.BadParameter(f"{path} must contain a mapping")
    return document


def _parse_parameters(assignments: list[str]) -> Record:
    """``name=value`` pairs; the value is read as a YAML scalar (0.01, 32, true, text)."""
    parameters: Record = {}
    for assignment in assignments:
        name, separator, raw = assignment.partition("=")
        if not separator or not name:
            raise typer.BadParameter(f"{assignment!r} is not name=value")
        value = yaml.safe_load(raw)
        if not isinstance(value, bool | int | float | str):
            raise typer.BadParameter(f"{assignment!r}: the value must be a number, boolean or text")
        parameters[name] = value
    return parameters


def _event_line(record: Record) -> str:
    return (
        f"{record['seq']:>6}  {record['timestamp_utc']}  {record['type']:<16}  "
        f"{record['subject_id']}  {record['actor']}"
    )


def _run_event_line(record: Record) -> str:
    """An event of one run, with what it says (the queued event carries the whole run)."""
    if record["type"] == "RUN_QUEUED":
        return _event_line(record)
    said = json.dumps(record["payload"], sort_keys=True)
    return f"{_event_line(record)}  {said if len(said) <= 240 else said[:239] + '…'}"


def _all_pages(client: ApiClient, path: str, params: Record, key: str) -> Record:
    """Follow the cursor of a log or resource reading to the end of what is recorded so far."""
    items: list[Record] = []
    while True:
        page: Record = client.get(path, params)
        items.extend(page[key])
        if not page["has_more"]:
            return {key: items, "next_cursor": page["next_cursor"], "complete": page["complete"]}
        params = {**_without_tail(params), "after": page["next_cursor"]}


def _without_tail(params: Record) -> Record:
    return {name: value for name, value in params.items() if name != "tail"}


def _watch(
    client: ApiClient,
    run_id: str,
    *,
    on_line: Callable[[Record], None],
    timeout: float | None,
    poll: float = 0.5,
) -> Record:
    """Hand over a run's output as it is recorded until the run has ended; return the run."""
    deadline = None if timeout is None else time.monotonic() + timeout
    cursor = 0
    status: str | None = None
    asked_for_supervisors = False
    while True:
        record: Record = client.get(f"/v1/runs/{run_id}")
        if record["status"] != status:
            status = record["status"]
            typer.echo(f"run {run_id}: {status}", err=True)
        page = client.get(f"/v1/runs/{run_id}/logs", {"after": cursor, "limit": 5000})
        for line in page["lines"]:
            on_line(line)
        cursor = page["next_cursor"]
        if page["complete"]:
            final: Record = client.get(f"/v1/runs/{run_id}")
            if final["status"] != status:
                typer.echo(f"run {run_id}: {final['status']}", err=True)
            return final
        if status == "queued" and not asked_for_supervisors:
            asked_for_supervisors = True
            if client.get("/v1/workers")["alive"] == 0:
                typer.echo(
                    "no supervisor is alive: the run stays queued until "
                    "`numericos worker run` is started",
                    err=True,
                )
        if deadline is not None and time.monotonic() > deadline:
            raise StillRunning
        if not page["has_more"]:
            time.sleep(poll)


def _watch_to_the_end(
    as_json: bool, api_url: str | None, run_id: str, *, quiet: bool, timeout: float | None
) -> None:
    """Follow a run until it ends, print it, and exit with the code of how it ended."""

    def on_line(line: Record) -> None:
        if not quiet:
            # In machine mode stdout carries only the final document.
            typer.echo(_log_text(line), err=as_json)

    try:
        record = _api(
            as_json,
            api_url,
            lambda client: _watch(client, run_id, on_line=on_line, timeout=timeout),
        )
    except StillRunning:
        typer.echo(f"run {run_id} had not ended after {timeout} s; it keeps going", err=True)
        raise typer.Exit(EXIT_STILL_RUNNING) from None
    except KeyboardInterrupt:
        typer.echo(
            f"stopped watching; run {run_id} keeps going "
            f"(stop it with `numericos run cancel {run_id}`)",
            err=True,
        )
        raise typer.Exit(EXIT_INTERRUPTED) from None
    _emit(record, as_json, _run_detail)
    code = RUN_EXIT_CODES[record["status"]]
    if code:
        raise typer.Exit(code)


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
            help="Restart on source changes (development), applying new migrations each time.",
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
                "NUMERICOS_MIGRATE_ON_START": "1" if migrate else "0",
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


def _await_schema(settings: Settings, timeout: float) -> None:
    """Wait until the database has the schema this code expects. The API migrates it; two
    processes migrating the same file would race, so the supervisor only waits."""
    expected = migrations.head_revision()
    engine = make_engine(settings.db_path)
    deadline = time.monotonic() + timeout
    announced = False
    try:
        while (current := migrations.current_revision(engine)) != expected:
            if time.monotonic() > deadline:
                typer.echo(
                    f"error: {settings.db_path} is at schema {current}, this supervisor needs "
                    f"{expected}; start the API (`numericos serve`) or run `numericos db upgrade`",
                    err=True,
                )
                raise SystemExit(1)
            if not announced:
                announced = True
                typer.echo(
                    f"waiting for {settings.db_path} to reach schema {expected} (now {current}); "
                    "the API applies migrations when it starts",
                    err=True,
                )
            time.sleep(0.25)
    finally:
        engine.dispose()


def supervise(
    data_dir: str | None, max_parallel: int, poll_interval: float, schema_timeout: float
) -> None:
    """Body of ``worker run``. A top-level function: ``--reload`` starts it in a new process."""
    # UTC like every other timestamp of NumericOS; only our own messages below warnings.
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)sZ %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("numericos").setLevel(logging.INFO)
    settings = Settings(data_dir=Path(data_dir)) if data_dir is not None else Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _await_schema(settings, schema_timeout)
    supervisor = Worker(settings, max_parallel=max_parallel, poll_interval=poll_interval)
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, request_stop)
    supervisor.start()
    typer.echo(
        f"supervisor {supervisor.id} serving {settings.data_dir} ({max_parallel} run(s) at a time)",
        err=True,
    )
    try:
        supervisor.run_forever(lambda: stop_requested)
    finally:
        supervisor.stop()
        typer.echo(
            f"supervisor {supervisor.id} stopped; runs in progress continue under their monitors",
            err=True,
        )


@worker.command("run")
def worker_run(
    data_dir: DataDirOption = None,
    max_parallel: Annotated[
        int, typer.Option("--max-parallel", min=1, max=64, help="Runs executed at the same time.")
    ] = 1,
    poll_interval: Annotated[
        float, typer.Option("--poll-interval", min=0.05, max=60, help="Seconds between rounds.")
    ] = 0.5,
    schema_timeout: Annotated[
        float,
        typer.Option(
            "--schema-timeout",
            min=0,
            help="Seconds to wait for the API to bring the database to the expected schema.",
        ),
    ] = 60.0,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Restart on source changes (development). Runs in progress are not interrupted.",
        ),
    ] = False,
) -> None:
    """Start a supervisor: it executes queued runs and records how they go (server side).

    Stopping it does not stop the runs. Each run has its own monitor process, which keeps
    observing and bounding it; the next supervisor takes the run over from its files.
    """
    arguments = (
        str(data_dir) if data_dir is not None else None,
        max_parallel,
        poll_interval,
        schema_timeout,
    )
    if reload:
        run_process(
            Path(__file__).resolve().parents[1],  # the numericos package
            target=supervise,
            args=arguments,
            watch_filter=PythonFilter(),
        )
        return
    supervise(*arguments)


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


@project.command("trust")
def project_trust(
    project_id: Annotated[str, typer.Argument(metavar="PROJECT_ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Allow NumericOS to execute commands in the project's directory.

    Running an experiment runs the project's code with your permissions. Trust is given to one
    exact directory and is withdrawn automatically when the project's code path changes.
    """
    path = f"/v1/projects/{project_id}"
    current = _api(json_, api_url, lambda client: client.get(path))
    if current["root_path"] is None:
        raise typer.BadParameter("the project has no code path; set one with `project update`")
    if not yes:
        typer.confirm(
            f"Allow NumericOS to execute commands in {current['root_path']}?", abort=True, err=True
        )
    body = {"version": current["version"], "root_path": current["root_path"]}
    data = _api(json_, api_url, lambda client: client.post(f"{path}:trust-execution", body))
    _emit(data, json_, _project_detail)


@project.command("untrust")
def project_untrust(
    project_id: Annotated[str, typer.Argument(metavar="PROJECT_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Stop accepting new runs for the project. Runs that already started keep going."""
    path = f"/v1/projects/{project_id}"

    def revoke(client: ApiClient) -> Record:
        version = int(client.get(path)["version"])
        result: Record = client.post(f"{path}:revoke-execution-trust", {"version": version})
        return result

    _emit(_api(json_, api_url, revoke), json_, _project_detail)


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


@hypothesis.command("add")
def hypothesis_add(
    project_id: ProjectOption,
    title: Annotated[str, typer.Option("--title", help="Short name of the hypothesis.")],
    claim: Annotated[str, typer.Option("--claim", help="What is asserted.")],
    rationale: Annotated[str, typer.Option("--rationale")] = "",
    prediction: Annotated[str, typer.Option("--prediction")] = "",
    falsification: Annotated[
        list[str] | None,
        typer.Option("--falsification", help="An outcome that would contradict it. Repeatable."),
    ] = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """State a falsifiable hypothesis. It starts as 'proposed'."""
    body = {
        "title": title,
        "claim": claim,
        "rationale": rationale,
        "prediction": prediction,
        "falsification": falsification or [],
    }
    data = _api(
        json_, api_url, lambda client: client.post(f"/v1/projects/{project_id}/hypotheses", body)
    )
    _emit(data, json_, _hypothesis_detail)


@hypothesis.command("list")
def hypothesis_list(
    project_id: ProjectOption, json_: JsonFlag = False, api_url: ApiUrlOption = None
) -> None:
    """List a project's hypotheses."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/projects/{project_id}/hypotheses"))
    _emit(
        data,
        json_,
        lambda d: "\n".join(_hypothesis_line(item) for item in d["hypotheses"]) or "no hypotheses",
    )


@hypothesis.command("show")
def hypothesis_show(
    hypothesis_id: Annotated[str, typer.Argument(metavar="HYPOTHESIS_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show one hypothesis."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/hypotheses/{hypothesis_id}"))
    _emit(data, json_, _hypothesis_detail)


@experiment.command("add")
def experiment_add(
    file: Annotated[
        Path, typer.Argument(metavar="FILE", help="Experiment contract (YAML or JSON).")
    ],
    project_id: ProjectOption,
    name: Annotated[
        str | None, typer.Option("--name", help="Default: 'name' in the file, else its stem.")
    ] = None,
    hypothesis_id: Annotated[
        str | None, typer.Option("--hypothesis", help="The hypothesis this experiment tests.")
    ] = None,
    reuse: Annotated[
        bool,
        typer.Option(
            "--reuse",
            help="If the project already has this name with exactly this contract, return it.",
        ),
    ] = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Register an experiment from a contract file.

    The file is a numericos.experiment.v1 protocol; it may also carry 'name' and 'hypothesis_id'.
    """
    body = _experiment_body(file, name, hypothesis_id)
    path = f"/v1/projects/{project_id}/experiments{'?reuse=true' if reuse else ''}"
    data = _api(json_, api_url, lambda client: client.post(path, body))
    _emit(data, json_, _experiment_detail)


@experiment.command("run")
def experiment_run(
    file: Annotated[
        Path, typer.Argument(metavar="FILE", help="Experiment contract (YAML or JSON).")
    ],
    project_id: ProjectOption,
    param: Annotated[
        list[str] | None,
        typer.Option("--param", "-P", help="name=value for an independent variable. Repeatable."),
    ] = None,
    seed: Annotated[int | None, typer.Option("--seed", min=0)] = None,
    label: Annotated[str, typer.Option("--label", help="Free text, e.g. 'baseline'.")] = "",
    code_ref: Annotated[
        str | None, typer.Option("--code-ref", help="Commit to execute (branch, tag or SHA).")
    ] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="Return as soon as the run is queued.")
    ] = False,
    timeout: TimeoutOption = None,
    quiet: QuietFlag = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Register the experiment of a contract file, queue one run of it and follow the run.

    Repeating the command does not duplicate the experiment: the one with this name and
    exactly this contract is used again, so all its runs stay comparable under one protocol.
    The exit code says how the run ended (see `numericos run watch`).
    """
    body = _experiment_body(file, None, None)
    submission = {
        "parameters": _parse_parameters(param or []),
        "seed": seed,
        "label": label,
        "code_ref": code_ref,
    }

    def register_and_queue(client: ApiClient) -> Record:
        registered = client.post(f"/v1/projects/{project_id}/experiments?reuse=true", body)
        queued: Record = client.post(f"/v1/experiments/{registered['id']}/runs", submission)
        return queued

    data = _api(json_, api_url, register_and_queue)
    if detach:
        _emit(data, json_, _run_detail)
        return
    _watch_to_the_end(json_, api_url, data["id"], quiet=quiet, timeout=timeout)


@experiment.command("list")
def experiment_list(
    project_id: ProjectOption, json_: JsonFlag = False, api_url: ApiUrlOption = None
) -> None:
    """List a project's experiments."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/projects/{project_id}/experiments"))
    _emit(
        data,
        json_,
        lambda d: (
            "\n".join(_experiment_line(item) for item in d["experiments"]) or "no experiments"
        ),
    )


@experiment.command("show")
def experiment_show(
    experiment_id: Annotated[str, typer.Argument(metavar="EXPERIMENT_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show one experiment and its protocol."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/experiments/{experiment_id}"))
    _emit(data, json_, _experiment_detail)


@run.command("submit")
def run_submit(
    experiment_id: Annotated[str, typer.Argument(metavar="EXPERIMENT_ID")],
    param: Annotated[
        list[str] | None,
        typer.Option("--param", "-P", help="name=value for an independent variable. Repeatable."),
    ] = None,
    seed: Annotated[int | None, typer.Option("--seed", min=0)] = None,
    label: Annotated[str, typer.Option("--label", help="Free text, e.g. 'baseline'.")] = "",
    code_ref: Annotated[
        str | None,
        typer.Option(
            "--code-ref", help="Commit to execute (branch, tag or SHA) instead of the default."
        ),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Repeating the command returns the same run."),
    ] = None,
    watch: Annotated[
        bool,
        typer.Option("--watch", "-w", help="Follow the run until it ends; the exit code says how."),
    ] = False,
    timeout: TimeoutOption = None,
    quiet: QuietFlag = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Queue one run of an experiment and return at once; a supervisor executes it.

    With --watch the command stays until the run has ended, printing its output, and exits
    with 0 only if the program ended normally (see `numericos run watch`).
    """
    body = {
        "parameters": _parse_parameters(param or []),
        "seed": seed,
        "label": label,
        "code_ref": code_ref,
    }
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    data = _api(
        json_,
        api_url,
        lambda client: client.post(f"/v1/experiments/{experiment_id}/runs", body, headers=headers),
    )
    if watch:
        _watch_to_the_end(json_, api_url, data["id"], quiet=quiet, timeout=timeout)
        return
    _emit(data, json_, _run_detail)


@run.command("list")
def run_list(
    experiment_id: Annotated[
        str | None,
        typer.Option("--experiment", "-e", help="All runs of this experiment, oldest first."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project", "-p", help="The newest runs of this project, newest first."),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, max=500, help="With --project: how many.")
    ] = 50,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """List the runs of an experiment, or the newest runs of a whole project."""
    if (experiment_id is None) == (project_id is None):
        raise typer.BadParameter("give exactly one of --experiment and --project")
    if experiment_id is not None:
        path, params = f"/v1/experiments/{experiment_id}/runs", None
    else:
        path, params = f"/v1/projects/{project_id}/runs", {"limit": limit}
    data = _api(json_, api_url, lambda client: client.get(path, params))
    _emit(data, json_, lambda d: "\n".join(_run_line(item) for item in d["runs"]) or "no runs")


@run.command("show")
def run_show(
    run_id: Annotated[str, typer.Argument(metavar="RUN_ID")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show one run: its status, parameters and exact argument vector."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/runs/{run_id}"))
    _emit(data, json_, _run_detail)


@run.command("status")
def run_status(run_id: RunArgument, json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """Print the status of a run, and why if it did not end normally. Returns at once."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/runs/{run_id}"))
    _emit(
        data,
        json_,
        lambda d: d["status"] + (f": {d['status_reason']}" if d["status_reason"] else ""),
    )


@run.command("export")
def run_export(
    run_id: Annotated[str, typer.Argument(metavar="RUN_ID")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write here instead of stdout.")
    ] = None,
    api_url: ApiUrlOption = None,
) -> None:
    """Export the run record: the run with its provenance and protocol, as JSON."""
    data = _api(True, api_url, lambda client: client.get(f"/v1/runs/{run_id}/record"))
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(text, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    typer.echo(f"wrote {output}", err=True)


@run.command("rerun")
def run_rerun(
    run_id: Annotated[str, typer.Argument(metavar="RUN_ID")],
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Queue a run with the same commit, parameters and seed as RUN_ID."""
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    data = _api(
        json_,
        api_url,
        lambda client: client.post(f"/v1/runs/{run_id}:rerun", None, headers=headers),
    )
    _emit(data, json_, _run_detail)


@run.command("cancel")
def run_cancel(
    run_id: RunArgument,
    reason: Annotated[str, typer.Option("--reason", help="Why; recorded with the request.")] = "",
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Ask for a run to be stopped, and return at once.

    A queued run is cancelled immediately. A running program gets SIGTERM on its whole process
    group and SIGKILL after the grace period of its protocol; the run becomes 'cancelled' when
    the program is gone. Follow it with `numericos run watch`.
    """
    data = _api(
        json_, api_url, lambda client: client.post(f"/v1/runs/{run_id}:cancel", {"reason": reason})
    )
    if data["cancel_requested_at"] is None:
        typer.echo(
            f"run {run_id} had already ended ({data['status']}); nothing was cancelled", err=True
        )
    _emit(data, json_, _run_detail)


@run.command("watch")
def run_watch(
    run_id: RunArgument,
    timeout: TimeoutOption = None,
    quiet: QuietFlag = False,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Follow a run until it ends: status changes on stderr, the program's output as it arrives.

    The exit code says how the run ended: 0 succeeded, 10 failed, 11 cancelled, 12 timed out,
    13 lost, 14 not finished within --timeout. 'succeeded' means the program ended normally,
    not that its result is valid. With --json the output lines go to stderr and stdout carries
    one document, the run.
    """
    _watch_to_the_end(json_, api_url, run_id, quiet=quiet, timeout=timeout)


@run.command("logs")
def run_logs(
    run_id: RunArgument,
    follow: Annotated[
        bool, typer.Option("--follow", "-f", help="Keep printing until the run has ended.")
    ] = False,
    tail: Annotated[
        int | None, typer.Option("--tail", min=1, max=10000, help="Start at the last N lines.")
    ] = None,
    stream: Annotated[
        list[LogStream] | None,
        typer.Option("--stream", "-s", help="Only this stream. Repeatable."),
    ] = None,
    plain: Annotated[
        bool, typer.Option("--plain", help="Only the text, without arrival time and stream.")
    ] = False,
    json_: Annotated[
        bool,
        typer.Option("--json", help="One JSON document; with --follow, one JSON line per line."),
    ] = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Print what a run wrote: every line with its arrival time (UTC) and its stream.

    Lines the program printed as metric records are part of the output and are shown too.
    """
    path = f"/v1/runs/{run_id}/logs"
    params = _given(
        tail=tail, stream=[item.value for item in stream] if stream else None, limit=5000
    )
    show: Callable[[Record], str] = (lambda line: str(line["text"])) if plain else _log_text

    if not follow:
        data = _api(json_, api_url, lambda client: _all_pages(client, path, params, "lines"))
        if json_:
            typer.echo(json.dumps(data, indent=2, sort_keys=True))
            return
        for line in data["lines"]:
            typer.echo(show(line))
        if not data["lines"]:
            typer.echo("no output recorded", err=True)
        return

    def print_until_the_end(client: ApiClient) -> None:
        query = params
        while True:
            page = client.get(path, query)
            for line in page["lines"]:
                typer.echo(json.dumps(line, sort_keys=True) if json_ else show(line))
            if page["complete"]:
                return
            query = {**_without_tail(query), "after": page["next_cursor"]}
            if not page["has_more"]:
                time.sleep(0.5)

    try:
        _api(json_, api_url, print_until_the_end)
    except KeyboardInterrupt:
        return


@run.command("resources")
def run_resources(
    run_id: RunArgument,
    tail: Annotated[
        int | None, typer.Option("--tail", min=1, max=10000, help="Only the last N samples.")
    ] = None,
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """Show the samples of a run's process tree: CPU, resident memory, processes, threads."""
    params = _given(tail=tail, limit=5000)
    data = _api(
        json_,
        api_url,
        lambda client: _all_pages(client, f"/v1/runs/{run_id}/resources", params, "samples"),
    )
    _emit(
        data,
        json_,
        lambda d: "\n".join(_sample_line(item) for item in d["samples"]) or "no samples recorded",
    )


@run.command("events")
def run_events(run_id: RunArgument, json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """Show what happened to a run, in ledger order: queued, started, limits, finished, ..."""
    data = _api(
        json_, api_url, lambda client: client.get(f"/v1/runs/{run_id}/events", {"limit": 1000})
    )
    _emit(
        data,
        json_,
        lambda d: "\n".join(_run_event_line(item) for item in d["events"]) or "no events",
    )


@artifact.command("list")
def artifact_list(
    run_id: Annotated[str, typer.Option("--run", "-r", help="Run whose files are listed.")],
    json_: JsonFlag = False,
    api_url: ApiUrlOption = None,
) -> None:
    """List the files a finished run left: its records, provenance files and results."""
    data = _api(json_, api_url, lambda client: client.get(f"/v1/runs/{run_id}/artifacts"))
    _emit(
        data,
        json_,
        lambda d: (
            "\n".join(_artifact_line(item) for item in d["artifacts"])
            or "no files registered (they are listed when the run ends)"
        ),
    )


@artifact.command("get")
def artifact_get(
    artifact_id: Annotated[str, typer.Argument(metavar="ARTIFACT_ID")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write here instead of stdout.")
    ] = None,
    api_url: ApiUrlOption = None,
) -> None:
    """Download one file of a run."""

    def fetch(client: ApiClient) -> int:
        written = 0
        with client.stream(f"/v1/artifacts/{artifact_id}/content") as chunks:
            if output is None:
                for chunk in chunks:
                    written += sys.stdout.buffer.write(chunk)
                return written
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as sink:
                for chunk in chunks:
                    written += sink.write(chunk)
        return written

    size = _api(False, api_url, fetch)
    if output is not None:
        typer.echo(f"wrote {output} ({_size(size)})", err=True)


@worker.command("list")
def worker_list(json_: JsonFlag = False, api_url: ApiUrlOption = None) -> None:
    """List supervisors and whether one is alive to start queued runs."""
    data = _api(json_, api_url, lambda client: client.get("/v1/workers"))
    _emit(
        data,
        json_,
        lambda d: (
            "\n".join(_worker_line(item) for item in d["workers"])
            or "no supervisor has run yet: start one with `numericos worker run`"
        ),
    )


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
