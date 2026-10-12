# NumericOS architecture (living document)

Status: **M0 accepted** on 2026-10-12 (tag `m0-gate`, evidence in
`docs/milestones/M0-gate.md`). The active milestone is M3; ADR-0004 records why it precedes M1
and M2. M3 so far: T01 (typed hypotheses, experiments and runs; the experiment contract; queued
runs), T02 (provenance of code, inputs and environment; explicit execution trust), T03 (the
supervisor: runs are executed, observed, bounded, cancellable and recovered after a restart)
and T04 (scientific metrics emitted by the program or parsed from its output, guardrails,
coverage per level, two worked examples). Validators arrive with T05: until then a run shows
what was measured, not whether its result is valid. Everything below describes
what exists; later milestones extend this file instead of replacing it. Roadmap and acceptance
gates live in `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md` and `milestones/`.

## Repository layout

```text
pyproject.toml, uv.lock        Python distribution "numericos" (see ADR-0001)
alembic.ini                    developer entry point for authoring migrations
src/numericos/
  config.py                    Settings (NUMERICOS_* environment variables)
  core/                        public schemas (Pydantic), enums, typed IDs, typed errors
  persistence/                 engine policy, ORM models, repositories, unit of work, migrations
  events/                      ledger row builder, in-process wake-up notifier, replay-then-live
                               iteration (`stream.follow`)
  provenance/                  read-only Git access, code capture, input checksums, environment
  executor/                    the per-run monitor with its metric collector, the worker,
                               launch preparation, outcome classification, artifact collection
  observability/               cursor reads of the files a monitor appends to; coverage
examples/                      worked experiments: heat2d-python, sparse-cg-cpp (contract,
                               program, derivations)
  services/                    use cases (projects, cards, research entities, runs,
                               observations): the only business logic
  api/                         FastAPI app factory, routers, error envelope, correlation middleware
  cli/                         `numericos` command line (HTTP client; `serve`, `db` and
                               `worker run` are server side)
tests/                         pytest: unit, persistence, api (TestClient), cli and integration
                               (real server subprocess)
contracts/openapi.v1.json      exported public contract (generated, committed, drift-checked)
apps/web/                      React + TypeScript + Vite GUI (npm project)
  src/api/                     schema.d.ts (generated from the contract), typed client, query hooks
  src/components/, src/pages/  shell, project list, project page, board, dialogs
  e2e/                         Playwright journeys against a real API process
docs/, milestones/, skills/    specification pack (product invariants, briefs, canonical skills)
```

Dependency direction inside `src/numericos`: `core <- persistence <- events <- services <- api`;
`cli` only speaks HTTP (it shares `core` vocabularies, never `persistence` or `services`).
`executor` uses `core`, `persistence`, `events` and `provenance`; services read its file layout
and write cancellation requests, and the worker never imports services. The monitor imports
only the layout, its specification and the executable lookup, so it starts quickly and needs
no database.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `NUMERICOS_DATA_DIR` | `~/.numericos` | local-first directory; the database is `<data_dir>/numericos.db` |
| `NUMERICOS_HOST` | `127.0.0.1` | bind address; loopback by default, never exposed remotely |
| `NUMERICOS_PORT` | `8765` | API port |
| `NUMERICOS_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON list of browser origins |
| `NUMERICOS_API_URL` | `http://127.0.0.1:8765` | base URL used by the CLI |
| `NUMERICOS_SSE_HEARTBEAT_SECONDS` | `15` | keep-alive and ledger re-read interval of event streams |
| `VITE_API_URL` (web) | `http://127.0.0.1:8765` | API base URL baked into the GUI |

`numericos serve --ephemeral` uses a fresh temporary data directory (demos, e2e tests).
`numericos serve --reload` (what `make api` runs) restarts the server when a file of the
`numericos` package changes; migrations are applied at startup and after every restart.
`numericos worker run --reload` (what `make worker` runs) does the same for the supervisor.
Restarting a supervisor never interrupts a run. A supervisor does not migrate the database: it
waits (`--schema-timeout`, 60 s by default) until the API has brought it to the schema it
expects, and exits with an explanation otherwise.

Tooling: `uv` manages the Python environment in `./.venv`; the Makefile and the Playwright config
export `UV_PROJECT_ENVIRONMENT` explicitly because a global value in the developer's shell would
otherwise redirect `uv sync` into an unrelated environment.

## Persistence

SQLite in WAL mode, one file per data directory. Engine policy (`persistence/engine.py`): on every
connection `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=FULL`, `busy_timeout=5000`;
pysqlite's implicit `BEGIN` is disabled and every transaction starts with `BEGIN IMMEDIATE`
(ADR-0002). Timestamps are stored as `YYYY-MM-DDTHH:MM:SS.ffffffZ` text through `UTCDateTime`;
naive datetimes are rejected at bind time.

### Schema (migration `0001`)

| Table | Columns | Notes |
| --- | --- | --- |
| `projects` | `id` PK, `name`, `research_question`, `description`, `root_path` NULL, `is_demo`, `version`, `created_at`, `updated_at` | `root_path` is a reference, never opened; `is_demo` marks seeded data |
| `board_cards` | `id` PK, `project_id` FK (RESTRICT), `card_type`, `title`, `description`, `workflow_status`, `sort_order`, `entity_ref` NULL, `version`, `created_at`, `updated_at` | CHECK constraints hold the closed vocabularies; index `(project_id, workflow_status, sort_order)`; no validity column by design |
| `events` | `seq` PK AUTOINCREMENT, `event_id` UNIQUE, `project_id` FK, `event_type`, `subject_id`, `actor`, `producer`, `severity`, `correlation_id`, `schema_version`, `payload` JSON, `timestamp_utc` | append-only; `seq` is the cursor; indexes on `(project_id, seq)`, `subject_id`, `correlation_id` |

Vocabularies (`core/enums.py`): card types `task | hypothesis | experiment | issue | decision`;
workflow statuses `backlog | planned | active | review | completed | blocked` (operational, never
scientific validity); event types in UPPER_SNAKE like the adapter contract (`PROJECT_CREATED`,
`CARD_MOVED`, `RUN_FINISHED`, ...; the full list is in "Use cases and their events"); severities
`debug | info | warning | error`.

IDs are `<prefix>_<ULID>` strings: `prj_`, `card_`, `evt_`, `cor_`, `hyp_`, `exp_`, `run_`,
`wrk_`, `art_`, `ser_`, `ases_` and `msg_` in use; `res_`, `ann_`, `ctx_` reserved for later
entities (`core/ids.py`). No empty tables are created ahead of their milestone.

### Conversations with the agent (migration `0006`)

| Table | Columns | Notes |
| --- | --- | --- |
| `agent_sessions` | `id` PK, `project_id` FK, `title`, `provider`, `permission_mode`, `model` NULL, `native_session_id`, `cwd`, `system_prompt`, `version`, `created_at`, `updated_at` | one provider session per conversation; `native_session_id` is chosen by NumericOS before the first turn; `cwd` is the trusted root at creation |
| `messages` | `id` PK, `session_id` FK, `project_id` FK, `role`, `status`, `status_reason`, `markdown`, `prompt_message_id`, `correlation_id`, `model_requested`, `effort`, `model`, `plan_usage` JSON, `activity` JSON, `activity_dropped`, `files_read` JSON, `files_written` JSON, `permission_denials` JSON, `cost_usd`, `usage` JSON, `num_turns`, `structured_output` JSON, supervision (`worker_id`, `pid`, `process_started_at`, `started_at`, `finished_at`, `heartbeat_at`, `cancel_requested_at`, `cancel_reason`, `exit_code`, `ingest` JSON), `version`, `created_at`, `updated_at` | a user message is the prompt (`final` at once); an assistant message is a turn: `queued | running | final | failed | cancelled | interrupted`; `markdown` is immutable once the turn ended; `model_requested` and `effort` are what the turn was started with, `model` what the provider reported, `plan_usage` the account's plan windows as last reported |
| `agent_policies` (`0007`) | `project_id` PK FK, `provider`, `tasks` JSON, `version`, `created_at`, `updated_at` | `{task: {model, effort}}` for every task (`conversation`, `clarify`, `resolve`, `theory`, `file_description`, `execution_description`, `plan`); null takes the provider's default. `agent_sessions` gained `task` and `effort` (overrides of the policy) in the same revision |

### Documents of the agent (migration `0008`)

| Table | Columns | Notes |
| --- | --- | --- |
| `documents` | `id` PK, `project_id` FK, `kind`, `doc_key`, `title`, `summary`, `category` NULL, `markdown`, `status`, `status_reason`, `instructions`, `subject_sha` NULL, `sources` JSON, `session_id`, `message_id`, `pending_message_id`, `model`, `generated_at`, `version`, `created_at`, `updated_at` | one row per project, kind (`theory`, `file_description`, `plan`) and key (the file's path for a description); `sources` is `[{path, sha}]`, the files the content was written from with their content hashes; `pending_message_id` is the turn writing the next content; `version` counts how many times content was written; status `generating | ready | failed` says whether there is content, never whether it is current |

The same revision adds `board_cards.origin` (`user | agent`) and `messages.json_schema` (the
schema a structured turn must answer in).

### Comments (migration `0009`)

| Table | Columns | Notes |
| --- | --- | --- |
| `annotations` | `id` PK, `project_id` FK, `target_type`, `target_id`, `target_version`, `kind`, `status`, `status_reason`, `body`, `start_offset`, `end_offset`, `quote`, `prefix`, `suffix`, `anchor_state`, `response_markdown`, `message_id`, `pending_message_id`, `responded_at`, `version`, `created_at`, `updated_at` | a comment on a passage of an answer (`message`) or of a document; offsets are Unicode code points of the Markdown source of `target_version`; kinds `clarification | change | note`; status `open | pending | answered | resolved | declined | dismissed`; `anchor_state` `attached | detached` |

The same revision adds `agent_sessions.target_type`, `target_id`, `target_version`: the text a
Clarify or Resolve session is about. Revision `0010` adds `messages.files_created` and
`files_moved`: the new files a turn left in the repository, and the ones moved out since.

### Unit of work and ordering

`UnitOfWork` (one per mutation) exposes one repository per table (`projects`, `cards`,
`events`, `hypotheses`, `experiments`, `runs`, `workers`, `artifacts`, `metric_series`,
`agent_sessions`, `messages`, `agent_policies`, `documents`, `annotations`);
`record()` appends the ledger row inside the transaction and `commit()` performs one COMMIT, then
wakes subscribers. Card placement is computed by `persistence/ordering.place()` and persisted by
`CardRepository.reindex()`, which renumbers the destination column (`index * 1000`) and writes
only rows whose rank changed.

### Migrations

Alembic scripts live in `src/numericos/persistence/migrations/` with named constraints and batch
mode enabled. They are applied by `numericos serve` at startup and again after every `--reload`
restart (`--no-migrate` skips both), or by `numericos db upgrade`; `numericos db current`
reports the current and expected revision. Before a database that already holds data is moved
to a newer revision, the file is copied to `numericos.db.before-<revision>.bak`. The test suite
runs `alembic check` and migrates a populated database of the previous revision, so models and
migrations cannot drift. Authoring a revision: `uv run alembic revision --autogenerate -m "..."`
(uses `alembic.ini`).

Revisions: `0001` projects, board cards, events; `0002` hypotheses, experiments, runs and
`events.run_id`; `0003` run provenance (code, inputs, environment, reproduced run) and
`projects.execution_trusted_at`; `0004` run supervision (worker, process identities, times,
cancellation, exit, outcome, resource summary, read offsets), `workers` and `artifacts`;
`0005` `metric_series` (one summary row per run and metric) and `runs.metric_report`; `0006`
`agent_sessions` and `messages`; `0007` `agent_policies`, session overrides, what a turn was
started with and what it consumed of the plan; `0008` `documents`, the origin of a card and the
schema of a structured turn; `0009` `annotations` and the target of a session; `0010` what a
turn left in the repository.

## Events

`events/ledger.py` builds rows from an `EventContext` (actor, correlation ID, producer).
`events/notifier.py` is a per-process wake-up signal: a committing thread calls `publish()` after
the durable commit, and subscribers re-read the ledger by cursor. The notifier carries no data,
so delivery can never precede durability.

`events/stream.py` turns that into a replay-then-live iteration: every event after a cursor, in
`seq` order, then each new one as it is committed. It clears the wake flag before each read (a
commit during the read is not lost) and re-reads after every heartbeat, which bounds the delay
for events committed by another process (ADR-0003).

The supervisor commits from its own process. `events/watcher.py` lets the API notice: one
thread asks SQLite for `PRAGMA data_version`, which changes whenever another connection
commits, and reports the new ledger head to the notifier, which wakes every subscriber. Nothing
is delivered from there; subscribers still read by cursor. Run events therefore reach an open
stream within a fraction of a second instead of at the next heartbeat.

### Event stream

`GET /v1/events` with `Accept: text/event-stream` is the Server-Sent Events view of the same
ledger the JSON page reads:

```text
retry: 2000

id: 3
data: {"event_id":"evt_...","seq":3,"project_id":"prj_...","type":"CARD_MOVED",...}

: ping - 2026-10-12 10:10:09+00:00
```

- The stream starts after `max(after, Last-Event-ID)`, replays what is already recorded, then
  follows. A reconnect with `Last-Event-ID` (or `after`) delivers exactly the missed events.
- Delivery is in order and at-least-once for a client that resumes from the last `seq` it
  processed; clients de-duplicate by `event_id`. Exactly-once is not claimed.
- Answered before the first byte: unknown project (404), `before`/`limit`/`order=desc` in
  stream mode or a malformed `Last-Event-ID` (422), and a cursor beyond the ledger head
  (409 `CURSOR_AHEAD`), which can only come from another ledger.
- Open streams end promptly when the server is asked to stop, so restarts are not held up.

## Research entities (M3)

| Entity | What it is | Rules |
| --- | --- | --- |
| Hypothesis (`hyp_`) | A falsifiable claim with rationale, prediction, falsification conditions and assumptions | Created `proposed`. Its epistemic status (`proposed`, `supported`, `contradicted`, `inconclusive`) cannot be set by hand: it will change only through recorded evidence and decisions (M3-T05). It is unrelated to any workflow status |
| Experiment (`exp_`) | A protocol that tests a hypothesis, or characterises a baseline when it has none | The protocol can be replaced only while the experiment has no runs (`PROTOCOL_FROZEN` afterwards). A different protocol is a different experiment |
| Run (`run_`) | One concrete execution: parameters, seed, exact argument vector, the digest of the protocol it ran under | Created `queued`; statuses `queued`, `starting`, `running`, `succeeded`, `failed`, `cancelled`, `timed_out`, `lost`. `succeeded` means the process ended normally, never that the result is valid |

One commit is not one experiment is not one run: a hypothesis can have several experiments, an
experiment many runs, and many runs can share a code revision.

### The experiment contract

`numericos.experiment.v1` (`core/experiment.py`) states the question, the expected observation
and the falsification conditions; the **independent variables** with the values the experiment
will use and the **controls** that stay fixed; how one run is **executed** (argument vector with
`{name}` placeholders, working directory, which code, environment, input files, environment
probes, build commands); the **metrics** with unit and who measures them (`instrumentation`,
`parser`, `supervisor`); output **parsers**; **guardrails** (what to do on NaN or infinity, and
explicit numeric bounds with a patience); and the **limits** of a run. No threshold has a
default: a guardrail or limit exists only if the contract states it, except the wall-clock
limit, which is mandatory.

The contract is validated as a whole: every placeholder must be a declared variable, a control
or `{seed}`; a metric must be measurable by what the contract declares; a guardrail must refer
to a declared metric. Its canonical JSON has a SHA-256 **digest** that every run records.

A run is derived from the contract, not typed freely: it gets all controls plus exactly one
*declared* value for every independent variable. A missing variable, an undeclared value, an
attempt to override a control or an unknown name is a 422 and queues nothing. The command is
never a shell line.

Submitting a run returns at once. With an `Idempotency-Key` header the submission is
repeatable: the same key and request return the run created the first time (200,
`Idempotency-Replayed: true`); the same key with a different request is `IDEMPOTENCY_CONFLICT`.

### Provenance: what exactly ran

A run answers three questions with recorded facts (ADR-0005).

**Which code.** By default a run executes an exact commit. The ref is resolved to a full SHA
when the run is created, so a moving branch cannot change a queued run, and the files are
exported from that commit rather than taken from the working tree. A submission may name its
own commit (`code_ref`): that is how a candidate and a baseline run under one protocol. If the
working tree had uncommitted changes at submission, the run says so and also says they were not
executed. An experiment may instead choose `working_tree` mode; the supervisor then records, at
start, the commit under the tree, a binary patch of the uncommitted changes with its SHA-256,
and the untracked files (digests, plus an archive up to 64 MB), which together rebuild the
executed tree. When such a run ends, the supervisor checks whether HEAD or the changes to
tracked files are still the recorded ones and says so on the run (`changed_during_run`,
`RUN_SOURCE_CHANGED`); files the program wrote beside its sources do not count as an edit.

**Which inputs.** Declared input files are hashed when the run starts; an expected SHA-256 in
the protocol is enforced.

**Which environment.** Host facts (platform, CPU, cores, memory), the program file that
`argv[0]` resolves to with its digest, the outputs of the protocol's probe commands, and the
run's environment variables. The program file is looked up when the program starts, after the
build commands, so a compiled program is identified by the binary that ran. A run gets a small
base environment plus what the protocol declares or asks to inherit, nothing else;
secret-looking values are redacted in the record. Values written in the protocol's `env` are
part of the contract and are stored as written: a secret is passed with `inherit_env`. The
directory of the Python environment NumericOS itself runs in is removed from the inherited
`PATH`: a run that says `python3` gets the user's interpreter, not the one of the tool that
supervises it. A project with its own environment names its interpreter in the command, or
creates it in a build command (`build: [[uv, sync, --frozen]]`, then `.venv/bin/python`).

NumericOS only reads the user's repository (`provenance/git.py`): no checkout, reset, clean,
stash, commit or fetch, and no index refresh.

`GET /v1/runs/{id}/record` exports the run with its provenance and protocol;
`POST /v1/runs/{id}:rerun` queues a run with the same commit, parameters and seed.

### Execution trust

Running an experiment runs the project's code with the user's permissions. No run can be queued
until the project's `root_path` has been trusted by an explicit action that repeats the exact
path. The path must be the top of a Git work tree. Changing `root_path` withdraws the trust.
There is no sandbox: trust means the command runs as the user.

## Execution and observation of runs (M3-T03)

ADR-0006 records the decisions; this section describes what runs.

```text
numericos serve            API: queues runs, records cancellation requests, serves observations
numericos worker run       supervisor: prepares runs, starts monitors, records what they write
  python -m numericos.executor.monitor RUN_DIR      one per run, detached, files only
    the program            in its own process group
```

**Life of a run.** `POST /v1/experiments/{id}/runs` creates it `queued` and returns. A worker
claims it (`starting`), prepares its directory, and starts its monitor. The monitor runs the
build commands, then the program (`running`, `RUN_STARTED`). When the program has ended the
monitor writes the outcome and the worker closes the run (`RUN_FINISHED`) as `succeeded`,
`failed`, `timed_out` or `cancelled`. `lost` is the end of a run whose monitor and program are
both gone without a recorded outcome. Each status and failure class is defined in ADR-0006.

**Run directory** `<data_dir>/runs/<run_id>/`:

| File | Written by | Content |
| --- | --- | --- |
| `spec.json` (0600) | worker | argument vector, working directory, real environment, build commands, limits |
| `monitor.json` | monitor | its PID and start time; created exclusively, so a run has one monitor |
| `launch.stamp` | monitor | touched just before the program starts |
| `started.json` | monitor | PID, start time and process group of the program; the program file with its digest |
| `output.jsonl` | monitor | one record per output line: arrival time, stream (`o`, `e`, build `b`), text |
| `resources.jsonl` | monitor | samples of the process tree: CPU, resident memory, processes, threads, I/O |
| `journal.jsonl` | monitor | what the monitor did: limits exceeded, signals sent, output cut, leftovers, metric anomalies |
| `metrics/<name>.jsonl` | monitor | the samples of one metric: arrival time, value or kind of non-finite value, step, time |
| `metrics.json` | monitor | the series so far in short, counts and diagnostics; rewritten about once a second |
| `exit.json` | monitor | exit code or signal of the program, why it ended, usage totals, output counts |
| `cancel.json` | API or worker | a request to stop the program |
| `code/` | worker | the exported commit (`ref` mode); the program's working directory is inside it |
| `outputs/` | the program | results; its path is `$NUMERICOS_OUTPUT_DIR` |
| `environment/`, `code.diff`, `untracked.tar` | worker | probe outputs; the working-tree record |

The program also gets `NUMERICOS_RUN_ID`, `NUMERICOS_RUN_DIR`, `NUMERICOS_CODE_DIR` and
`NUMERICOS_PROJECT_ROOT`, and `PYTHONUNBUFFERED=1` unless the protocol sets it otherwise.

**What is observed (level L0).**

- Output lines with arrival time and stream; a line longer than 1 MiB is cut and marked.
- Exit code or signal of the program.
- Two durations. `wall_seconds` runs from the start of the monitor to its end, build commands
  included, and is what the wall-clock limit bounds. `program_seconds` is the program alone,
  from just before it was started to the moment its exit was noticed (a `SIGCHLD` wake-up
  makes that immediate).
- Exact totals for the program: its CPU time (user and system) and the largest resident set of
  one of its processes, as the operating system reports them when the program is reaped
  (`wait4`). They cover the program and the descendants it waited for, not the build.
- Samples of the process tree at the protocol's interval: CPU use since the previous sample,
  resident memory summed over the tree, processes, threads and, where the platform offers it,
  I/O. Each is tagged `build` or `program`. The first comes one interval after the command
  started, so a run shorter than the interval has exact totals and no samples. A peak between
  two samples is missed: the sampled maximum is tree-wide but approximate.

Nothing numerical is inferred from these. Numbers with a scientific meaning come from the
program or from its output, as described next.

**Limits and stopping.** See ADR-0006, decision 5. The wall-clock limit covers the build
commands and the program.

**Recovery.** See ADR-0006, decision 7. Workers are listed by `GET /v1/workers` with whether
they are alive; without a live one queued runs wait, and the CLI says so.

**Artifacts.** Registered when the run ends (`GET /v1/runs/{id}/artifacts`), each with kind,
media type, size and SHA-256, and downloadable. Kinds: `output`, `resources`, `journal`,
`outcome`, `metric_summary`, `metric_series`, `monitor_log`, `code_diff`, `untracked_files`,
`environment_probe`, `result`.

## Scientific metrics (M3-T04)

ADR-0007 records the decisions; `docs/instrumentation.md` is the guide for someone who wants
to make a program observable. In short:

- **Sources.** A sample of a metric comes from a record the program emits
  (`numericos.metric.v1`, level L2), from a parser of the contract applied to an output line
  (L1), or from the supervisor's own measurement of the process (`wall_time`, `cpu_time`,
  `max_rss`). The contract declares each metric with its unit and its source.
- **Collection.** `executor/collector.py` runs inside the monitor. It validates records
  strictly, reads numbers the way solvers print them, stores non-finite values as typed
  samples, writes one file per metric and keeps a summary of every series.
- **Guardrails.** Explicit bounds of the contract, evaluated on every sample by the monitor:
  a bound with a patience in consecutive samples, and the policy for NaN and infinity. A halt
  ends the run `failed / numerical_instability`. NumericOS assumes no threshold.
- **Storage.** Samples stay in the run directory, bounded by `limits.max_metrics_mb`. The
  table `metric_series` holds one row per run and metric: source, unit, counts, first and
  last sample, extremes. The worker updates it from the monitor's summary while the run goes
  on.
- **Coverage.** `GET /v1/runs/{id}/metrics` answers per level (L0 process, L1 parsers, L2
  instrumentation, L3 validators) and per declared metric with `observed`, `partial`,
  `waiting`, `missing` or `not_configured`, and lists what the program emitted beyond the
  contract and what was wrong with its records. L3 is `not_configured` until validators exist.
- **Examples.** `examples/heat2d-python` (explicit scheme for the 2D heat equation: stable
  and unstable time steps on both sides of a limit derived for this scheme, a guardrail that
  is an invariant of the scheme, closed forms for norm and error) and `examples/sparse-cg-cpp`
  (conjugate gradient in double and single precision: a run that exits normally and reports
  convergence without having reached it). Their contracts are run by the test suite.

## Use cases and their events

`services/` holds the business rules; routes only translate HTTP. Every successful mutation writes
exactly one event in the same transaction; a request that changes nothing writes no event and
bumps no version.

| Use case | Event | Payload |
| --- | --- | --- |
| create project | `PROJECT_CREATED` | `project` |
| update project | `PROJECT_UPDATED` | `project`, `changed_fields` |
| create card (appended to its column) | `CARD_CREATED` | `card` |
| edit card content | `CARD_UPDATED` | `card`, `changed_fields` |
| move card (alone or together with an edit) | `CARD_MOVED` | `card`, `changed_fields`, `from`, `to`, `reindexed` siblings |
| state / reword a hypothesis | `HYPOTHESIS_CREATED` / `HYPOTHESIS_UPDATED` | `hypothesis`, `changed_fields` |
| define / change an experiment | `EXPERIMENT_CREATED` / `EXPERIMENT_UPDATED` | `experiment`, `changed_fields` |
| queue a run | `RUN_QUEUED` | `run`; the event carries `run_id` |
| ask for a run to be stopped | `RUN_CANCEL_REQUESTED` (and `RUN_FINISHED` at once if it was still queued) | `reason`, `status_when_requested` |
| trust / revoke execution for a project | `PROJECT_EXECUTION_TRUSTED` / `PROJECT_EXECUTION_TRUST_REVOKED` | `project` |
| open / change a conversation with the agent | `AGENT_SESSION_STARTED` / `AGENT_SESSION_UPDATED` | `session`, `changed_fields` |
| set the model and effort per task | `AGENT_POLICY_UPDATED` | `tasks`, `version` |
| move the files a turn left in the repository to the NumericOS folder | `AGENT_FILES_MOVED` | `paths`, `destination`, `session_id` |
| ask the agent for the theory, a plan, or the description of files | `DOCUMENT_GENERATION_QUEUED` (one per turn; with the session and turn events of the turn it queues) | `kind`, `keys`, `message_id`, `session_id` |
| the turn of a document ends (written by the supervisor, or by the API for a turn cancelled before it started) | `DOCUMENT_GENERATION_FINISHED`; for a plan, also `CARD_CREATED` / `CARD_UPDATED` / `CARD_MOVED` per card | `kind`, `written`, `failed` (`{key: reason}`), `message_id`, `session_id`; for a plan `cards_created`, `cards_changed`, `entries_skipped` |
| send a prompt (records the user message, queues the turn) | `AGENT_TURN_QUEUED` | `session_id`, `prompt_message_id`, `prompt_excerpt`, `permission_mode`; the subject is the turn |
| ask for a turn to be stopped | `AGENT_TURN_CANCEL_REQUESTED` (and `AGENT_TURN_FINISHED` at once if it was still queued and unclaimed) | `reason`, `status_when_requested` |

| comment on a passage; reword or withdraw a comment | `ANNOTATION_CREATED` / `ANNOTATION_UPDATED` | `annotation` (without its context and answer), `changed_fields` |
| Clarify or Resolve the open requests on a text | `ANNOTATIONS_SENT` (with the session and turn events of the turn it queues) | `task`, `target_type`, `target_id`, `annotation_ids`, `permission_mode`, `message_id`, `session_id` |
| the turn of a Clarify or Resolve ends | `ANNOTATIONS_ANSWERED` | `task`, `answered`, `reopened` (`{id: reason}`), `applied`, `declined`; when the text was rewritten `document_id`, `document_version`, `comments_attached`, `comments_detached` |

Events of a turn written by the supervisor (`producer: worker`, the correlation ID of the request
that queued it): `AGENT_TURN_STARTED` (`pid`, `session_id`, `resume`, `permission_mode`),
`AGENT_TURN_FINISHED` (`status`, `status_reason`, `session_id`, `model`, `cost_usd`,
`num_turns`, `files_written`, `permission_denials`, `agent_started`, `subtype`,
`duration_ms`), `AGENT_TURN_ADOPTED` and `AGENT_TURN_REQUEUED` as for runs. The actions of the
agent (every tool call with its target, the text between actions) are recorded on the message,
not as ledger events: a turn makes dozens of them.

Events of a run written by the supervisor (`producer: worker`, actor `worker:<id>`, the
correlation ID of the request that queued the run, `run_id` set):

| Event | When | Payload |
| --- | --- | --- |
| `RUN_STARTED` | the program is running | `pid`, `argv`, `code_sha` |
| `RUN_FINISHED` | the run reached a final status | `status`, `failure_class`, `status_reason`, `exit_code`, `signal`, `wall_seconds`, `code_sha`, `program_started`, `results_not_listed` if any |
| `RUN_LIMIT_EXCEEDED` | a limit was passed and the program is being stopped | `limit`, `value`, `threshold` |
| `RUN_OUTPUT_TRUNCATED` | output beyond the limit is no longer stored | `limit_bytes` |
| `RUN_LEFTOVER_PROCESSES` | the program ended and left processes behind, which were stopped | |
| `RUN_SOURCE_CHANGED` | working-tree run: HEAD or the tracked changes moved while it ran | `detail` |
| `RUN_ADOPTED` | another worker took the run over | `previous_worker_id`, `worker_id` |
| `RUN_REQUEUED` | its worker stopped before the program was started | `reason` |
| `RUN_MONITOR_LOST` | the monitor is gone while the program still runs | `pid` |
| `RUN_METRIC_NON_FINITE` | a metric became NaN or infinite (first time per metric; severity error) | `metric`, `value`, `step`, `action` |
| `RUN_GUARDRAIL_VIOLATED` | a bound of the contract was violated for its patience (error if it halts, warning if it records) | `metric`, `bound`, `threshold`, `value`, `non_finite`, `step`, `consecutive`, `action` |
| `RUN_METRICS_TRUNCATED` | samples beyond the storage limit are no longer stored | `limit_bytes` |
| `RUN_PROGRAM_EVENT` | the program emitted a `numericos.event.v1` record | `name`, `message`, `severity`, `step` |

`project` and `card` are the public representations after the change. Placement rules: a new
`workflow_status` moves the card to `position` in that column (appended when omitted); `position`
alone reorders inside the current column; out-of-range positions are clamped; moving a card to
where it already is changes nothing. Only the moved card's `version` is bumped.

## Public API

| Method and path | Purpose |
| --- | --- |
| `GET /v1/health` | process liveness, database and schema revision state |
| `POST /v1/projects`, `GET /v1/projects` | create, list in creation order |
| `GET /v1/projects/{project_id}`, `PATCH /v1/projects/{project_id}` | read, update (needs `version`) |
| `GET /v1/projects/{project_id}/board` | `workflow_statuses` in column order and `cards` in board order |
| `POST /v1/projects/{project_id}/cards` | create a typed card at the end of its column |
| `GET /v1/cards/{card_id}`, `PATCH /v1/cards/{card_id}` | read, edit and/or move (needs `version`; optional `project_id` assertion) |
| `POST`, `GET /v1/projects/{project_id}/hypotheses`; `GET`, `PATCH /v1/hypotheses/{id}` | state, list, read, reword (needs `version`) |
| `GET /v1/projects/{id}/contract-files`; `POST /v1/projects/{id}/experiments:import` | experiment contracts found as files in the project's repository; register one from a file of the project or from pasted text |
| `GET /v1/experiments/{id}/series` | the metric summaries of all runs of an experiment, to put them side by side |
| `POST`, `GET /v1/projects/{project_id}/experiments`; `GET`, `PATCH /v1/experiments/{id}` | define by protocol (`?reuse=true` returns the experiment that already has this name and exactly this protocol), list, read; rename, relink or replace the protocol while there are no runs |
| `POST`, `GET /v1/experiments/{id}/runs`; `GET /v1/runs/{id}` | queue a run (optional `Idempotency-Key`, optional `code_ref`), list, read |
| `GET /v1/projects/{id}/runs?limit=` | the newest runs of a project across its experiments |
| `POST /v1/runs/{id}:cancel` | ask for a run to be stopped (optional `reason`); returns at once |
| `GET /v1/runs/{id}/logs?after=&tail=&limit=&stream=` | output lines by cursor: `lines`, `next_cursor`, `has_more`, `complete` |
| `GET /v1/runs/{id}/resources?after=&tail=&limit=` | resource samples by cursor, same shape |
| `GET /v1/runs/{id}/metrics` | the series of a run in short, coverage per level and per declared metric, diagnostics |
| `GET /v1/runs/{id}/metrics/{name}?after=&tail=&limit=` | samples of one metric by cursor |
| `GET /v1/runs/{id}/metrics/{name}/overview?buckets=` | a whole series reduced to a bounded number of buckets, for charts |
| `GET /v1/runs/{id}/events?after=&limit=&order=` | the ledger events of one run |
| `GET /v1/runs/{id}/artifacts`; `GET /v1/artifacts/{id}/content` | the files a finished run left; download one |
| `GET /v1/workers` | supervisors, whether each is alive, and how many can start queued runs |
| `GET /v1/runs/{id}/record`; `POST /v1/runs/{id}:rerun` | export the run record; queue a repetition with the same commit, parameters and seed |
| `POST /v1/projects/{id}:trust-execution`, `:revoke-execution-trust` | allow, or stop allowing, commands to be executed in the project directory |
| `GET /v1/agents/capabilities` | whether the agent command can be started where NumericOS runs (found by running `--version`, never assumed), and the models and effort levels it can be asked for |
| `GET`, `PUT /v1/projects/{id}/agent-policy` | the model and effort per task of the project; `PUT` needs the current `version` (0 the first time) and refuses a model or effort the provider does not offer (422) |
| `POST`, `GET /v1/projects/{id}/agent-sessions`; `GET`, `PATCH /v1/agent-sessions/{id}` | open a conversation (needs a trusted directory; `permission_mode`, optional `model`), list newest first, read, rename or change the mode (needs `version`) |
| `POST`, `GET /v1/agent-sessions/{id}/messages`; `GET /v1/messages/{id}` | send a prompt (201 with the queued turn; 409 `SESSION_BUSY` while the previous turn is open, `AGENT_UNAVAILABLE` without the command), the messages in order, one message with everything observed |
| `POST /v1/messages/{id}:cancel` | ask for a turn to be stopped (optional `reason`); returns at once |
| `GET /v1/projects/{id}/theory`; `POST /v1/projects/{id}/theory:generate` | the theory document or nothing yet, with `stale` and `changed_sources` computed at the read; ask the agent to write it, or write it again (202; optional `instructions`; 409 `GENERATION_PENDING` while a turn is writing it) |
| `GET /v1/projects/{id}/plan`; `POST /v1/projects/{id}/plan:generate` | the notes of the last plan; ask the agent for a plan, shown the board as it is; its cards are put on the board when its turn ends |
| `GET /v1/projects/{id}/files` | the files of the project directory (tracked, or new and not ignored; at most 5000) with size, kind, content hash and the state of their description; counts per state |
| `POST /v1/projects/{id}/files:describe` | ask for descriptions: `paths`, or `scope` `undescribed`, `stale` or `all` (202 with how many files in how many turns; files being described are skipped; at most 400 per request) |
| `GET /v1/projects/{id}/files/description?path=`; `GET /v1/documents/{id}` | the whole description of one file; one document by ID |
| `GET /v1/projects/{id}/files/content?path=` | a file of the trusted project directory, to show it (an image); only regular files inside the directory, served with `nosniff` and a sandboxing policy |
| `GET /v1/annotations?target_type=&target_id=`; `POST /v1/annotations` | the comments on one text in the order of their passages, with the turn that is answering some of them; comment on a passage (`quote`, and `start_offset`/`end_offset` in code points, or a quote that occurs once) |
| `PATCH /v1/annotations/{id}`; `POST /v1/annotations/{id}:dismiss` | reword an open comment or change its kind (needs `version`); withdraw it |
| `POST /v1/annotations:clarify`, `:resolve` | send every open request of that kind on a text to the agent in one turn (202; `instructions`; for resolve `permission_mode` `edit` or `full`); 409 `SESSION_BUSY` while the previous ones are being answered |
| `GET /v1/projects/{id}/workspace` | the NumericOS folder of the project: its path, how it is named to people, whether it is inside the project, exists and is ignored by Git |
| `POST /v1/messages/{id}:move-created-files` | move the new files a turn left in the repository to the NumericOS folder (optional `paths`; all that are left otherwise); only files that turn created, still there and still untracked |
| `GET /v1/projects/{id}/agent-sessions?task=` | the conversations by default; `task=theory`, `file_description`, `plan` or `all` for the sessions in which documents were written |
| `GET /v1/events?project_id=&after=&before=&limit=&order=&run_id=` | one page of the ledger: `events`, `next_cursor`, `has_more`; with `Accept: text/event-stream` a replayable stream (`project_id`, `after`) |

Operation IDs equal the handler names (`create_project`, `update_card`, ...), so generated
clients get stable method names.

## Public API conventions

- Versioned prefix `/v1`; OpenAPI document at `/v1/openapi.json`, interactive docs at `/v1/docs`.
- `GET /v1/health` reports `status` (`ok` or `degraded`), `db` (`ok` or `unavailable`), the
  current and expected schema revision and the data directory. It always answers 200 while the
  process is alive; the fields say whether the database is usable.
- Every non-2xx response, including the framework's own 404/405/422/500, uses one envelope:

  ```json
  {"error": {"code": "NOT_FOUND", "message": "...", "details": {}, "correlation_id": "cor_..."}}
  ```

  Codes are stable UPPER_SNAKE identifiers: `VALIDATION_ERROR` (422), `NOT_FOUND` (404),
  `STALE_REVISION` (409, the `version` sent is not the current one; details carry both),
  `PROJECT_MISMATCH` (409, a record is not in the asserted project), `PROTOCOL_FROZEN` (409,
  the experiment already has runs), `IDEMPOTENCY_CONFLICT` (409, a key reused for another
  request), `EXECUTION_NOT_TRUSTED` (409, the project directory was not trusted for execution),
  `NOT_A_GIT_REPOSITORY` (409), `NOT_REPRODUCIBLE` (409, a working-tree run cannot be rerun
  automatically), `CURSOR_AHEAD` (409, a cursor beyond the ledger head or beyond what a run
  has recorded), `ARTIFACT_MISSING` (409, a registered file is no longer in its run
  directory), `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500).
- `X-Correlation-ID`: accepted from the client when it matches `[A-Za-z0-9_.-]{1,64}`, otherwise a
  `cor_<ULID>` is generated; always echoed on the response and stored on every event.
- `X-Actor`: label of the calling surface in the form `<surface>:<name>` (`web:local`,
  `cli:local`, `cli:seed`; default `api:unknown`). It is stored on every event the request causes;
  it is recorded, not trusted, on a loopback-only service. A malformed value is a 422.
- Request bodies reject unknown fields (`extra="forbid"`), so typos never silently no-op. In a
  PATCH an absent field means "keep"; `null` is accepted only for nullable fields.
- Updates require the record `version` (optimistic locking). Run submissions accept an
  `Idempotency-Key`; other creations do not yet.
- Timestamps are UTC with a `Z` suffix. Neither IDs nor timestamps depend on the host timezone
  or locale (CI runs the tests under a non-UTC `TZ`).

## CLI conventions

`numericos` is an HTTP client of the API, never a second backend. Server-side commands are
limited to `serve`, `db upgrade|current` and `worker run`. With `--json`, stdout carries exactly
one JSON document and diagnostics go to stderr. Exit codes: `0` success, `1` API error (the
envelope is printed on stderr), `2` usage error, `3` API unreachable.

A command that waits for a run (`run watch`, `run submit --watch`, `experiment run`) ends with
how the run ended: `0` succeeded, `10` failed, `11` cancelled, `12` timed out, `13` lost, `14`
not finished when `--timeout` expired (the run goes on). While waiting it prints the program's
output as it arrives; with `--json` that output goes to stderr and stdout carries the run.

| Command | Purpose |
| --- | --- |
| `numericos health` | reachability, version, database state |
| `numericos project list` / `add NAME` / `show ID` / `update ID` | projects |
| `numericos card add -p PROJECT -t TYPE --title T` / `list -p PROJECT` / `show ID` / `move ID` / `update ID` | board cards |
| `numericos events list -p PROJECT [--after N] [--limit N] [--desc]` | the ordered ledger |
| `numericos events follow -p PROJECT [--after N] [--limit N] [--json]` | replay from a cursor, then follow; JSON Lines with `--json`; on a broken stream it prints the `seq` to resume from and exits 3 |
| `numericos seed-demo` | one demo project flagged `is_demo` (explicit, idempotent, actor `cli:seed`) |
| `numericos hypothesis add -p PROJECT --title T --claim C` / `list` / `show ID` | hypotheses |
| `numericos experiment add FILE -p PROJECT` / `list -p PROJECT` / `show ID` | experiments from a contract file (YAML or JSON; it may carry `name` and `hypothesis_id`) |
| `numericos run submit EXPERIMENT_ID -P name=value [--seed N] [--label L] [--code-ref REF] [--idempotency-key K]` / `list -e EXPERIMENT` / `show ID` | queue and inspect runs |
| `numericos run export ID [-o FILE]` / `rerun ID` | the run record as JSON; a repetition with the same commit, parameters and seed |
| `numericos experiment run FILE -p PROJECT [-P name=value] [--detach]` | register the contract (reusing an identical one), queue one run and follow it to its end |
| `numericos run submit ... --watch` / `run watch ID [--timeout S] [--quiet]` | follow a run to its end; the exit code says how it ended |
| `numericos run status ID` / `run list -p PROJECT` / `run cancel ID [--reason R]` | status and reason; newest runs of a project; ask for a stop |
| `numericos run logs ID [-f] [--tail N] [-s STREAM] [--plain]` | output lines with arrival time and stream; `-f` follows until the run ends |
| `numericos run resources ID [--tail N]` / `run events ID` | resource samples; the ledger events of the run |
| `numericos run metrics ID` / `run metric ID NAME [-f] [--tail N]` | coverage, series and diagnostics of a run; the samples of one metric |
| `numericos artifact list -r RUN` / `artifact get ID [-o FILE]` | the files a run left; download one |
| `numericos worker run [--max-parallel N] [--data-dir D] [--reload]` / `worker list` | start a supervisor (server side); list supervisors and whether one is alive |
| `numericos project trust ID [--yes]` / `untrust ID` | allow or stop allowing execution in the project directory |

`update` and `move` use optimistic locking: without `--version` they read the latest version
first (last write wins); with `--version N` a concurrent change is reported as `STALE_REVISION`.

## GUI

The GUI is a client of the public API like any other; it holds no state of its own beyond a
query cache and never ships mock data.

- **Colour:** colour says what a thing is, the same way everywhere. Indigo is what can be
  pressed and what is selected. Each view has its colour and icon on its tab (plan indigo,
  theory violet, files sky, agent fuchsia, experiments cyan), and the tag of an event in the
  strip takes the colour of what it is about. Cards carry the colour of their type on a solid
  tag, on their edge and as a tint (task sky, hypothesis violet, experiment cyan, issue
  orange, decision pink; none green or red: a type never signals validity); columns carry
  the colour of the workflow status (Completed green, Blocked red, as on any Kanban board:
  about the work, not about the result). File kinds have a tag and an icon each; the state
  of a description is green when current, amber when the file changed, sky while written,
  red when it failed. Comments are sky (clarification), orange (change) and violet (note) on
  their tag, their card and their highlight in the text; a passage whose comment was dealt
  with turns green. Permission modes read as risk: read only green, edit files amber, full
  autonomy red. Tools in the agent's activity are tinted by family (looking, changing,
  running). Code blocks are coloured by language (rehype-highlight). What the process of a
  run did, and how far its observation reaches, stays without green: "ended normally" and
  "observed" are not verdicts, and unit tests assert it.
- **Routes:** `/` lists projects. `/projects/:projectId` frames the views of one project and
  owns its event stream: the board (index), `experiments`, `experiments/:experimentId`,
  `runs/:runId`, `agent` and `agent/:sessionId`. Any other path is a not-found page.
- **Shell:** left project navigation and a connection indicator that is always visible. The
  indicator is derived from polling `GET /v1/health`: `Connected` (with the API version, and a
  note when the database needs a migration), `Checking backend` or `Backend unreachable`. When
  the backend is unreachable a banner states that what is shown is the last state received at a
  given time, not live data, and every control that changes data is disabled.
- **Project page:** the research question and the project reference (code path and project ID)
  are shown on the board view; demo projects carry a "Demo data" label. The view tabs
  anticipate the roadmap: `Board`, `Experiments` and `Agent` are real views, `Timeline` and
  `Knowledge` are disabled buttons naming the milestone that delivers them. Nothing is
  pretend-functional.
- **Theory view:** the theory of the project rendered like a paper (a reading measure, serif
  text, numbered equations by KaTeX, figures of the repository with their captions, served
  from the project directory). Below it: version, model and time, the files it was written
  from, and a form to write it again with the instructions of the last request. When a source
  changed, an alert names the files and the text stays readable. While the agent writes, its
  actions are shown live, with a way to stop it and a link to its conversation.
- **Files view:** every file of the project by directory, with its kind (guessed from the name
  until a description says more: code, input, output, image, config, documentation), size,
  one-sentence summary and state: not described, being described, described, changed since,
  failed. A line says where NumericOS keeps what it generates about the project. A row opens
  to the whole description, to the image if it is one, and to "describe it again". Two buttons ask for all files not described and for all that changed; filters by
  path and kind. The directory is read only for a project that was trusted.
- **Comments:** the theory, every answer in a conversation and every file description is a
  commentable text (`components/comments/Commentable.tsx`). Selecting a passage shows a small
  bar: ask to clarify, request a change, add a note; the chosen one opens a text box under the
  selection, which stays marked. The page is rendered with marks of where each piece comes
  from in the source (`sourcePositions.ts`), and `lib/sourceMap.ts` turns a selection into a
  source range and back: exact to the character in plain text, a formula, code or an image
  whole. Passages are highlighted with the CSS Custom Highlight API, coloured by kind,
  without changing the page; a click on one brings its comment forward, and a click on a
  comment shows its passage. The list (beside a document, under an answer) has the two
  buttons: **Clarify (n)** sends the open clarifications at once; **Resolve (n)…** first says
  that files will be edited directly and asks which mode. While the agent answers, its
  actions are shown. A clarification appears right after the block of its passage, in a
  marked box that can be folded, and the text around it is untouched; a change request shows
  what the agent did or why it declined; a comment whose passage was rewritten says so.
- **Plan (the board):** a panel above the board asks the agent for a plan; its cards appear on
  the board marked "agent", its reasons stay in the panel. Cards are dragged by a handle
  between and inside columns (dnd-kit; a pure function turns what a card was dropped on into
  the placement the API takes), or moved without a pointer by the status select and the up and
  down buttons. The next request to the agent starts from the board as it was left.
- **Agent view:** the conversations of the project (newest first) and the one that is open.
  Before anything can be sent, the preconditions are shown as they are: the directory trusted,
  a supervisor alive, the agent command found. A prompt is recorded at once and the answer is
  a turn: queued (and the page says if no supervisor can serve it), working (every action of
  the agent as it is recorded: the file, the command, the pattern, whether it succeeded),
  answered (Markdown with mathematics rendered by KaTeX; raw HTML is not rendered), failed,
  stopped or interrupted, with the reason. An answer names the new files its turn left in the
  repository, if any, with a button that moves them to the NumericOS folder. Every answer
  shows the model that answered, the
  effort, the tokens used, what the turn would cost at list prices (a measure, not a charge:
  the owner has a subscription), its duration, and the use of the plan's 5-hour and 7-day
  windows as the provider reported it; what the permission mode refused is listed, never
  hidden. A working turn can be stopped with a recorded reason. The permission mode of a
  conversation (read only, edit files, full autonomy) is chosen when it starts and can be
  changed between turns. One turn at a time per conversation: the composer waits while the
  agent answers.
- **Models and effort per task:** a panel of the Agent view lists the kinds of task (conversation,
  clarify, resolve, theory page, file descriptions, execution description, plan) with a model
  and an effort each, chosen among what the provider offers (for Claude Code: Fable, Opus,
  Sonnet, Haiku and `low` to `max`; "provider default" leaves the choice to Claude Code's own
  settings). Rows of tasks whose feature is not built yet are shown, not editable. The
  composer shows the policy's choice for the conversation and lets one conversation override
  it; the answer records what the turn was started with.
- **Experiments view:** first the two preconditions of running anything, as they are: whether
  execution is allowed in the project directory (allowing it is a dialog that shows the exact
  path and needs an explicit confirmation) and whether a supervisor is alive. Then the
  registered experiments, the contract files found in the repository (one click registers
  one; an invalid one says why), and the newest runs of the project.
- **Experiment page:** the contract in words (what it asks, what a run does, what is measured
  and by whom, what stops a run), a form that queues a run from the declared values only and
  sends an idempotency key, and the runs of the experiment side by side with the last value
  of every declared metric.
- **Run page (Run Monitor):** status and reason; coverage per level with what is missing,
  undeclared or wrong; a chart for every metric with more than one sample and a table for
  quantities measured once; exact resource totals and charts of the samples; the output,
  closed until asked for; provenance; the run's events; its files with checksums. A run in
  progress can be stopped (with a recorded reason); a run of an exact commit can be repeated.
- **Honest wording:** `succeeded` is shown as "Ended normally" in a neutral colour, and the
  page says that no validator has judged the result. "Observed" in the coverage is not
  green. A failed run keeps everything observed and says so. Unit tests assert these.
- **Charts:** dependency-free SVG, built from pure functions (`lib/chart.ts`: axes, ticks,
  paths) that are unit-tested. A point of a long series is the last sample of a stretch, with
  the extremes of the stretch as a band behind the line. Where a sample is not finite the
  line breaks and a mark says so; nothing is interpolated across it. On a logarithmic axis
  values without a logarithm are left out and counted. Bounds of the contract are drawn as
  dashed lines. Resource charts include zero.
- **Following a run:** ledger events of the project refresh every query of the project, so a
  status change arrives through the stream. What a program produces between events (samples,
  output) is re-read every 2 s while the run is active, and never after it ended. Output and
  resource samples are followed by cursor (`useCursorFeed`), each reading continuing exactly
  where the previous one stopped.
- **Board:** one column per workflow status, in the order returned by the board endpoint; cards
  in the order the backend stores. A card shows its type and its workflow status and nothing
  about validity: no supported/refuted label exists anywhere in the GUI. Until drag and drop
  (M1) a card moves through its status select (appended to the destination column) and its
  up/down buttons (position in the column). Cards are created and edited in a dialog.
- **Writes:** every update sends the record `version`. A `STALE_REVISION` answer is explained to
  the person and the view is refreshed; a `VALIDATION_ERROR` shows the server's message next to
  the field. A mutation stays pending until the refreshed data is on screen, so a second action
  is never sent with an outdated version by accident.
- **Freshness:** a project page subscribes to the project's event stream. The stream is a
  wake-up signal, not a second source of state: to connect, the page reads the ledger head,
  subscribes right after it, and re-reads the project, the board and the recent events when the
  stream opens and on every event (de-duplicated by `event_id`). Changes made by the CLI or
  another tab therefore appear within a fraction of a second. If the stream fails, the page
  closes it, says "Live updates interrupted", polls every 5 seconds and retries the same
  sequence every 2 seconds. It never claims to be live while the backend is unreachable. The
  list of projects has no stream yet and is polled every 5 seconds.
- **Event strip:** below the board, the 20 newest entries of the project's ledger, newest first,
  each with its ledger position, time, a one-line description built only from the event's type
  and payload, and the actor. An event type the GUI does not know is shown by its recorded name.
- **Types:** request and response types come from `schema.d.ts`. The label maps for card types
  and workflow statuses are `Record`s over the generated unions, so a vocabulary change in the
  contract is a compile error until the GUI handles it.

## Contracts pipeline

Pydantic models in `numericos.core.schemas` are the single source of the public schema:
`numericos openapi --output contracts/openapi.v1.json` exports it and `npm run gen:api` derives
`apps/web/src/api/schema.d.ts`. CI fails when either committed file is stale (`make check-contracts`).

## Testing layers

| Layer | Tool | Scope |
| --- | --- | --- |
| Unit | pytest | IDs, ordering, schemas, notifier, replay-then-live iteration, SSE decoding |
| Persistence | pytest on a migrated temp SQLite | migrations (fresh, idempotent, round trip, `alembic check`), PRAGMAs, repositories, constraints, unit of work, publish-after-commit, sequence continuity across restarts |
| API | pytest + `TestClient` | projects, cards, placement, events paging, envelope, headers, CORS, health states, contract snapshot |
| Process | pytest + `LiveServer` (real `numericos serve` subprocess) | CLI contract and data commands, `events follow`, startup migration, concurrent writers, event stream (replay, `Last-Event-ID`, push, another process writing, refused cursors, prompt stop with subscribers), state and ledger across a restart |
| Examples | pytest running the shipped programs alone and, from their own contract files, under a supervisor | closed forms of norm and error of the heat scheme to round-off; time steps on both sides of the exact stability limit; a guardrail halt that leaves its evidence; overflow as typed samples; conjugate gradient in two precisions with the true residual far from the reported one; binary and compiler provenance |
| Execution | pytest with real monitor processes and real programs from a real Git repository; `LiveWorker` (real `numericos worker run` subprocess) where a supervisor must die | the monitor (output, limits, signals, process tree, leftovers, build, one monitor per run); the worker (recording, classification, cancellation, trust and input checks, working tree against commit, results next to the sources, binary identity, parallelism); recovery (supervisor killed and run taken over with complete output, orderly hand-over, lost monitor, re-queue, two supervisors competing for the queue, overtaken readings); API restarted during a run; run events on an open stream |
| Documents | pytest; the API alone, and the stand-in agent under a real supervisor | file kinds from names, prompts and schemas, content hashes (index, changed, new, missing, hashed once); the API (theory and plan requests, their sessions and prompts, pending and cancelled requests, the listing with kinds, sizes, hashes and counts, batches per turn, files outside the project refused, content served with its type); generation (theory with sources and hashes, stale after an edit or a deletion and current again after a rewrite, failure keeping the earlier text, descriptions with normalized paths, stale and updated, a file left out, a plan creating cards and a second one changing them) |
| NumericOS folder | pytest with the stand-in agent under a real supervisor | a helper file written to the folder with `git status` unchanged; the note of each kind of turn; caches redirected; a file left in the repository reported, the researcher's own untracked file and an edit of a tracked file not reported; move one, move the rest, refuse a file the turn did not create, leave a file committed since; documents mirrored as Markdown and rewritten after a Resolve; the folder neither listed nor described; the folder outside the project with `--add-dir` |
| Comments | pytest; pure anchor rules, and the stand-in agent under a real supervisor | locating a quote (once, by context, ambiguous, missing, code points); comments by quote and by offsets in passage order, refused places, reword and withdraw; Clarify (one turn, read-only, both requests and not the change, the text untouched, answers on the comments); a later Clarify continuing the session without the text, busy and nothing-to-send; a request left out, a failed turn and a cancelled one reopening comments; Resolve (file edited, applied and declined, the text rewritten and current, comments moved or detached); an answer commented and never rewritten; a text written again keeping or detaching comments |
| Agent | pytest with the stand-in command as a real subprocess of the supervisor | the adapter (argument vector per mode, resume and fork, folding of the stream, bounds); the API (capabilities, missing command, trust, sessions, one turn at a time, cancellation, validation); turns (everything observed and the turn's files, resume of the provider session, refusals of the mode recorded, failure, agent gone without an answer, stop while working, sessions in parallel, worker died after claiming, running turn taken over, cancelled before start); the CLI (`ask` follows and prints, exit codes, give up and cancel) |
| Web unit | Vitest (jsdom) | API client, error mapping, connection indicator, card (no validity label), projects page (empty, list, load failure), event descriptions (board, runs, guardrails, agent), event strip, stream hook (subscribe after the head, de-duplicate, reconnect, no retry on typed answers), cursor feed, chart geometry and the chart itself (breaks at non-finite samples, logarithmic axis, bands, bounds), number formats, coverage panel, status badge, execution panel, run page (normal end, failure, in progress, queued without a supervisor), Markdown (GFM, KaTeX inline and displayed, no raw HTML, safe links), message card (prompt, answer with facts and actions, working with stop, queued without supervisor, failure, refusals), agent view (conversation and composer, untrusted directory, missing command, empty), policy panel, theory view (empty, paper with figure and sources, stale, in progress, failed), files view (listing by directory, opening a file and an image, filters, asking with instructions, untrusted directory), drop placement of a dragged card, selection to source and back on really rendered Markdown (plain text, across formatting, formulas, code, escapes, code points), the commentable text (a selection becoming a comment with code-point offsets, a formula commented whole, the list with answers and counts, a clarification after its paragraph, another version not placed, Resolve asking first, Clarify in one click) |
| Browser | Playwright against a real API, a real supervisor and the Vite dev server, on a throwaway data directory | first run and empty state, create/move/reorder/edit with reload, stale edit, keyboard use, disabled future views, backend loss and recovery, pushed updates, event strip, polling fallback, project switch, a real API process restarted under an open page, CLI and browser on the same state; experiments: allow execution, register a contract from the repository, queue a run and read it back, a run stopped by a guardrail, a run followed while it goes on and stopped from the page; agent: a conversation held and rendered (mathematics, cost, actions, persisted across a reload), a refusal of the read-only mode shown, a working turn stopped from the page, model and effort per task chosen and used; documents: the theory written, rendered with its figure and marked stale after the code changed, then written again; files described, one changed and updated; a plan put on the board and a card dragged to another column, persisted; comments: a passage of the theory selected and commented, a word picked with the pointer, Clarify answering next to the passage with the text untouched, Resolve editing the file and rewriting the text with comments kept or detached; an answer of a conversation commented, clarified without growing the conversation, a comment withdrawn; the NumericOS folder: a helper script kept out of the repository, a stray file named on the answer and moved out with `git status` clean afterwards, the folder named on the Files page and not listed |

No fixtures or mocks live in application code; the GUI shows the real backend connection state.

## Security defaults

Loopback binding, CORS limited to the GUI origin, no secrets in fixtures or logs.
`NUMERICOS_DATA_DIR` is created on demand by `serve`/`db`/`worker run`. Project code is executed
only for a project whose directory was explicitly trusted, as an argument vector, never through
a shell, with a small base environment plus what the protocol declares or asks to inherit.
Trust is checked again when a run starts. There is no sandbox: a trusted command runs with the
user's permissions. `spec.json`, the one file that holds a run's real environment, is readable
by the user only; records and exports redact the values of secret-looking names. A downloaded
artifact is served as an attachment from inside its run directory and nowhere else.

## Conversations with the coding agent (M1-T01)

Design record: ADR-0008. The first provider is the Claude Code command line; the
provider-specific protocol stays in `agents/claude_code.py`, which builds the argument vector
of a turn (`claude -p --output-format stream-json --verbose`, the permission flags of the
session's mode, `--session-id` for the first turn and `--resume` afterwards,
`--append-system-prompt`, `--max-budget-usd`, optional `--model` and `--json-schema`) and folds
the records of its standard output into provider-neutral progress (`core/agents.py`: activity
items, files read and written, permission denials, the final result with cost and usage). The
model's hidden reasoning (`thinking` blocks) is not recorded.

The API never starts the agent. `services/agents.py` opens sessions (a trusted directory and an
available command are required; the native session ID is a UUID chosen by NumericOS), records
prompts and queues turns (one open turn per session), and cancels. The supervisor
(`agents/supervisor.py`, driven by `Worker.tick()` under the worker's identity) claims the oldest
queued turn of a session nobody is answering, writes the prompt (the person's text plus a note of
the mode of this turn) and the argument vector into `data_dir/agent-turns/<message_id>/`, starts
the agent detached with its output going to `stream.jsonl` and its standard error to
`stderr.log`, records the process identity (`process.json`: PID and start time), then reads the
stream between fenced transactions as it reads a monitor's files. A `result` record ends the
turn (`final`, or `failed` when the provider reports an error); a process that is gone without
one leaves the turn `interrupted` (or `cancelled` when a stop was requested), with the last line
of its standard error as the reason. Stopping is SIGTERM to the process group, SIGKILL after
five seconds. A worker that dies after claiming a turn is replaced: the next worker adopts the
turn, re-queues it if no process was started, or continues reading the running process.

`numericos agent` mirrors the API: `capabilities`, `sessions`, `new`, `ask` (follows the turn,
prints the actions as they are recorded on stderr and the answer on stdout; exit code `0`
answered, `10` failed, `11` stopped, `13` interrupted, `14` still going after `--timeout`),
`messages`, `show`, `cancel`.

Tests run a stand-in for the command (`tests/fake_claude.py`: the same flags, the same records,
no model), selected with `NUMERICOS_CLAUDE_COMMAND`; the browser tests start their API and
supervisor with it too. No test calls the real provider.

## Documents of the agent: theory, files, plan (M1-T04/T05/T07, first parts)

Three things the agent writes about a project are kept as documents, each asked for by a button
and never on its own: the **theory** (one per project), the **description of a file** (one
per path) and the notes of a **plan** (one per project; its cards go to the board).

`services/documents.py` queues the request: it opens a session of the task (`theory`,
`file_description`, `plan`; always `read_only`), queues a turn with the prompt of
`agents/prompts.py` (the task named on its first line, then what to write, then the
researcher's own instructions last) and marks the documents with the turn that will write them.
File descriptions are asked a few files per turn (`NUMERICOS_AGENT_FILES_PER_TURN`, 8), one
session per turn so that they run in parallel, with a JSON schema for the answer; a plan has a
schema as well (`rationale`, `cards` with an optional `id` of an existing card); the theory is
free Markdown that starts with its title. The model and effort are the policy's row of the
task; until a policy is saved the suggested one applies (Sonnet with low effort for file
descriptions, Sonnet with medium effort for plans, the provider's default elsewhere).

When the turn ends, in the same transaction, `agents/documents.complete` gives the documents
what was written: the theory takes the answer, its first level-1 heading as title and, as
sources, the files the agent read with the content hash each had at that moment; a file
description takes its entry of the structured answer (paths the agent gave as absolute are
made relative; a file left out is marked failed with the reason); a plan creates the new cards
at the end of their columns with `origin: agent`, applies the changes to cards named by `id`,
skips entries it cannot use and says how many. A turn that failed, was stopped or was
interrupted leaves the content of an earlier turn in place and records why the new one is
missing.

**Staleness is computed, never stored.** `provenance/git.content_hashes` gives the content
hash of files as they are now: from the index for tracked files `git status` reports unchanged,
by `git hash-object` (once per size and modification time) for changed and new files. A
document is stale when a source's hash differs or the file is gone, and says which files. A
file description compares the hash recorded when it was asked for (`subject_sha`) with the
file's hash now. Nothing is regenerated automatically: the pages mark what changed and offer
one click to update it, because every update is a call on the owner's account.

## The NumericOS folder of a project

Design record: ADR-0010. Everything NumericOS and its agent generate about a project is kept
in one folder (`agents/workspace.py`): `.numericos/` at the top of the project directory,
which ignores itself for Git through its own `.gitignore`, or
`<NUMERICOS_WORKSPACE_ROOT>/<project id>/` outside the project. It holds `scratch/` (what the
agent creates that is not a change to the project), `docs/` (the documents as Markdown:
`theory.md`, `plan.md`, `files/<path>.md`, written by the supervisor after the transaction
that changed them), `moved/` and `cache/`.

Every turn is told about the folder after its permission note (`workspace.note`): a turn that
may write is told to keep the repository clean and where to put what it generates; a turn
that writes a document from the project is told to leave the folder alone. The agent's
process gets `NUMERICOS_WORKSPACE`, `NUMERICOS_SCRATCH_DIR` and cache directories for Python,
mypy and ruff inside it. Before a turn that may write, the supervisor saves the untracked
files of the repository in the turn directory (`untracked.json`); when the turn ends it lists
them again, between the transactions, and what is new is recorded as `files_created`.
`services/agents.move_created_files` moves such files to `moved/<message id>/`, never one
that Git tracks since.

## Comments, Clarify and Resolve (M1-T02/T03)

Design record: ADR-0009. Every answer of the agent and every document it wrote can be
commented on any passage. `core/anchors.py` holds the two pure rules: the context of a range,
and where a quote is in a text (once: there; several times: where the kept context agrees
best, if one place agrees better than the others; otherwise nowhere). `agents/targets.py`
loads what a comment is attached to, an answer (a record: never rewritten) or a document.

`services/comments.py` creates comments (the quote must be exactly at the offsets given, or
occur once), rewords and withdraws open ones, and sends them: `send` picks the open requests
of one kind whose passage is still in the text, finds or opens the session of that task for
that version of the text, queues one turn with the prompt of `agents/prompts.py` (the text
between `--- document start ---` and `--- document end ---` on the first turn only, then one
numbered entry per request: its id, the passage, the passage in its surroundings, the request,
each as a JSON string on one line) and marks the comments pending. Clarify is read-only;
Resolve is `edit` or `full`.

`agents/comments.complete` runs in the transaction that ends the turn, after
`agents/documents.complete`: a clarification takes its answer; a change request takes the
agent's decision and summary; a comment the answer leaves out, or whose turn did not end
well, is open again with the reason. If Resolve returned a revised text for a document,
it becomes the document's next version (sources: the earlier ones and the files the turn read
or wrote, with the hashes the supervisor took between the transactions), and
`agents/anchoring.reanchor` looks for every comment of the document again in it. The same
re-anchoring runs when a document is written again from scratch.

## Deferred boundaries (documented, not built)

- **AgentAdapter** beyond Claude Code: a second provider (Codex `exec`), capability
  negotiation, `install_skills`; contract in `docs/AGENT_ADAPTER_CONTRACT.md`. Provider-specific
  IDs live on the session (`native_session_id`), never on Project/BoardCard.
- **SkillRegistry** (M1): `skill_id`, version or Git revision, `source_path`, SHA-256 content
  digest, compatibility flags, installation receipt; design in `docs/SKILL_ARCHITECTURE.md`.

## Known limitations

- **Single user, single API process.** No authentication; the API binds to loopback. Live
  wake-ups need `uvicorn --workers 1`. What a supervisor commits from its own process reaches
  subscribers through the ledger watcher within a fraction of a second, and at the next
  heartbeat at the latest.
- **Idempotency keys only for run submissions.** Other creations are protected by nothing but
  the caller: a retried `POST` of a project, card, hypothesis or experiment creates a second
  record (an experiment can be registered with `?reuse=true` instead).
- **No delete or archive** for projects and cards, and no cross-project move of a card.
- **Execution has no sandbox.** A trusted project's commands run with the user's permissions.
  `root_path` must be the top of a Git work tree; submodule and Git LFS contents are not part of
  an exported commit.
- **Supervision is local and by observation.** One host; limits are checked at the sampling
  interval, not enforced by the kernel; no CPU-core or GPU limit; no automatic retry; exports
  of commits are not pruned; a working-tree run's files in the project directory are not
  collected. ADR-0006 lists the consequences in full.
- **Metrics come from standard output and standard error.** Files a solver writes are not
  parsed. A program that emits more than about 160,000 records per second is slowed down to
  that rate. Guardrail rules look at consecutive samples of one metric only. No validator
  exists yet, so nothing states that a result is valid. ADR-0007 lists the consequences.
- **The list of projects is polled** every 5 seconds; only project pages have an event stream.
- **The event strip shows the 20 newest entries.** Older ones are read with
  `numericos events list` / `follow`. A full timeline view belongs to M3.
- **The run page re-reads, it does not stream samples.** While a run is active its metrics
  are re-read every 2 s and each chart asks for the whole series again in buckets. That is
  cheap for the series of the examples and wasteful for very long ones. The output view shows
  the last 300 lines and what follows; the whole output is a file of the run. Runs of an
  experiment are compared in a table of last values: plots across runs and verdicts belong to
  the validators ticket.
- **The repository is kept clean by instruction, observation and a button, not by a wall.**
  In `edit` and `full` mode the agent can write anywhere in the project: it is told to use
  the NumericOS folder, what it leaves elsewhere is named on its answer, and one click moves
  it out. A tool the agent starts in a way that ignores the environment can still write a
  cache next to the sources. A file created by someone else during a turn is listed as left
  by the turn. Programs run as experiments in `working_tree` mode write where they write.
- **Comments.** A selection inside a code block or a formula comments the whole block. A
  detached comment cannot be attached to another passage by hand. The notes of the plan and
  the cards of the board cannot be commented. Every answer of a conversation reads its own
  comments: a very long conversation makes as many small requests. Highlights need a browser
  with the CSS Custom Highlight API; without it the comments are only listed. Resolve edits
  files with nothing in between: what changed is in Git, and nothing reverts it.
- **Documents are updated on request, not by themselves.** A changed source marks a document
  stale; nothing is regenerated until a button is pressed. A regenerated or resolved document
  replaces the one before: earlier versions are not kept.
  The theory's sources are the files the agent opened with its Read tool; what it learned
  through a search is not a source. New figures are not produced: the theory can only include
  images that exist in the repository. A description of a file does not go stale when another
  file it mentions changes. A dragged card is placed when the server answers, not optimistically.
- **The agent runs with the user's permissions and account.** Every turn uses the owner's
  Claude account. With a subscription nothing is charged per turn: a turn consumes the plan's
  windows, which the answer shows as the provider reported them; the `cost_usd` figure is the
  list-price equivalent the provider computes, a measure of tokens, and
  `NUMERICOS_AGENT_MAX_BUDGET_USD` bounds that figure per turn (5 by default). The weight of a
  turn depends mostly on the model: measured on 2026-10-12, a trivial turn was 0.31
  USD-equivalent with Fable and 0.0025 with Haiku, most of it the system prompt of the first
  turn of a session (later turns read it from cache). The `edit` mode refuses commands, so the agent
  cannot run tests in it; `full` mode refuses nothing. What the agent changed in the repository
  is listed by name and visible in Git; nothing reverts it. The provider's own session files
  live under `~/.claude`, outside the data
  directory: a data directory copied to another machine resumes no session. The activity kept
  on a message is bounded to 400 items; the whole stream stays in the turn's file.
- **SQLite transactions serialise writers and readers** (`BEGIN IMMEDIATE`). Output and
  resource samples go to files, not to the database; the supervisor writes one short
  transaction per run and round. Measured on the development machine (2026-10-12, four runs in
  parallel, 200 output lines and 20 resource samples per second in total): `GET /v1/runs/{id}`
  took 0.7 ms at the median and 0.9 ms at the 99th percentile (5.4 ms at worst), a card
  creation 1.1 ms and 2.3 ms (7.4 ms at worst), the same as with no run in progress. Not
  measured: many more parallel runs, or a slow disk.

## Decisions

- ADR-0001: one Python distribution with module boundaries.
- ADR-0002: transactional event ledger, publish-after-commit, SQLite transaction policy and
  column renumbering.
- ADR-0003: Server-Sent Events as a replayable view of the ledger; cursor rules; the GUI uses
  the stream as a wake-up signal.
- ADR-0004: by the owner's decision, observability of code and experiments (M3) comes before
  agents (M1), knowledge (M2) and any further board work.
- ADR-0005: a run executes an exact commit exported for it (or, by explicit choice, the recorded
  working tree); NumericOS only reads the repository; execution needs explicit trust.
- ADR-0006: one monitor process per run and a worker that turns its files into durable state;
  process identity, stopping, status and failure classes, recovery, fenced transactions.
- ADR-0007: metrics are samples with a declared source, collected and guarded by the run's
  monitor; strict records, typed non-finite values, explicit guardrails, coverage per level.
- ADR-0010: everything NumericOS and its agent generate about a project goes to one folder
  that Git does not see; the agent is told so on every turn, the repository is watched for
  what a turn leaves in it, and one click moves that out.
- ADR-0009: a comment is a range of the Markdown source with its quote and context; the page
  carries marks that map a selection to the source; a rewritten text has its comments looked
  for again and never attached by guessing; Clarify and Resolve are one turn each for all the
  open requests on a text, in a session of their own.
- ADR-0008: by the owner's redirection, conversations with the coding agent and commentable
  documents come before validators; Claude Code's command line is the first adapter; the
  supervisor runs the agent; three permission modes; Clarify and Resolve as batched turns.
