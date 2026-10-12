# NumericOS architecture (living document)

Status: **M0 complete** (tickets T01-T05), pending the gate review recorded in
`docs/milestones/M0-gate.md`. Everything below describes
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
  services/                    use cases (projects, cards, events): the only business logic
  api/                         FastAPI app factory, routers, error envelope, correlation middleware
  cli/                         `numericos` command line (HTTP client; `serve`/`db` are server side)
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
`numericos` package changes; migrations are applied once, at startup.

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
scientific validity); event types `PROJECT_CREATED | PROJECT_UPDATED | CARD_CREATED |
CARD_UPDATED | CARD_MOVED` (UPPER_SNAKE like the adapter contract); severities
`debug | info | warning | error`.

IDs are `<prefix>_<ULID>` strings: `prj_`, `card_`, `evt_`, `cor_` in use; `hyp_`, `exp_`,
`run_`, `res_`, `ases_`, `msg_`, `ann_`, `ctx_`, `art_` reserved for later entities
(`core/ids.py`). No empty tables are created ahead of their milestone.

### Unit of work and ordering

`UnitOfWork` (one per mutation) exposes `projects`, `cards` and `events` repositories;
`record()` appends the ledger row inside the transaction and `commit()` performs one COMMIT, then
wakes subscribers. Card placement is computed by `persistence/ordering.place()` and persisted by
`CardRepository.reindex()`, which renumbers the destination column (`index * 1000`) and writes
only rows whose rank changed.

### Migrations

Alembic scripts live in `src/numericos/persistence/migrations/` with named constraints and batch
mode enabled. They are applied by `numericos serve` at startup (`--no-migrate` skips) or by
`numericos db upgrade`; `numericos db current` reports the current and expected revision. The
test suite runs `alembic check`, so models and migrations cannot drift. Authoring a revision:
`uv run alembic revision --autogenerate -m "..."` (uses `alembic.ini`).

## Events

`events/ledger.py` builds rows from an `EventContext` (actor, correlation ID, producer).
`events/notifier.py` is a per-process wake-up signal: a committing thread calls `publish()` after
the durable commit, and subscribers re-read the ledger by cursor. The notifier carries no data,
so delivery can never precede durability.

`events/stream.py` turns that into a replay-then-live iteration: every event after a cursor, in
`seq` order, then each new one as it is committed. It clears the wake flag before each read (a
commit during the read is not lost) and re-reads after every heartbeat, which bounds the delay
for events committed by another process (ADR-0003).

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
| `GET /v1/events?project_id=&after=&before=&limit=&order=` | one page of the ledger: `events`, `next_cursor`, `has_more`; with `Accept: text/event-stream` a replayable stream (`project_id`, `after`) |

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
  `PROJECT_MISMATCH` (409, the card is not in the asserted project), `CURSOR_AHEAD` (409, a
  stream cursor beyond the ledger head), `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500).
- `X-Correlation-ID`: accepted from the client when it matches `[A-Za-z0-9_.-]{1,64}`, otherwise a
  `cor_<ULID>` is generated; always echoed on the response and stored on every event.
- `X-Actor`: label of the calling surface in the form `<surface>:<name>` (`web:local`,
  `cli:local`, `cli:seed`; default `api:unknown`). It is stored on every event the request causes;
  it is recorded, not trusted, on a loopback-only service. A malformed value is a 422.
- Request bodies reject unknown fields (`extra="forbid"`), so typos never silently no-op. In a
  PATCH an absent field means "keep"; `null` is accepted only for nullable fields.
- Updates require the record `version` (optimistic locking). Idempotency keys are deferred to the
  asynchronous submissions of M3-M5.
- Timestamps are UTC with a `Z` suffix. Neither IDs nor timestamps depend on the host timezone
  or locale (CI runs the tests under a non-UTC `TZ`).

## CLI conventions

`numericos` is an HTTP client of the API, never a second backend. Server-side commands are
limited to `serve` and `db upgrade|current`. With `--json`, stdout carries exactly one JSON
document and diagnostics go to stderr. Exit codes: `0` success, `1` API error (the envelope is
printed on stderr), `2` usage error, `3` API unreachable.

| Command | Purpose |
| --- | --- |
| `numericos health` | reachability, version, database state |
| `numericos project list` / `add NAME` / `show ID` / `update ID` | projects |
| `numericos card add -p PROJECT -t TYPE --title T` / `list -p PROJECT` / `show ID` / `move ID` / `update ID` | board cards |
| `numericos events list -p PROJECT [--after N] [--limit N] [--desc]` | the ordered ledger |
| `numericos events follow -p PROJECT [--after N] [--limit N] [--json]` | replay from a cursor, then follow; JSON Lines with `--json`; on a broken stream it prints the `seq` to resume from and exits 3 |
| `numericos seed-demo` | one demo project flagged `is_demo` (explicit, idempotent, actor `cli:seed`) |

`update` and `move` use optimistic locking: without `--version` they read the latest version
first (last write wins); with `--version N` a concurrent change is reported as `STALE_REVISION`.

## GUI

The GUI is a client of the public API like any other; it holds no state of its own beyond a
query cache and never ships mock data.

- **Routes:** `/` lists projects; `/projects/:projectId` shows one project and its board; any
  other path is a not-found page.
- **Shell:** left project navigation and a connection indicator that is always visible. The
  indicator is derived from polling `GET /v1/health`: `Connected` (with the API version, and a
  note when the database needs a migration), `Checking backend` or `Backend unreachable`. When
  the backend is unreachable a banner states that what is shown is the last state received at a
  given time, not live data, and every control that changes data is disabled.
- **Project page:** the research question and the project reference (code path and project ID)
  are shown prominently; demo projects carry a "Demo data" label. The view tabs anticipate the
  roadmap: `Board` is active, `Experiments`, `Timeline`, `Agents` and `Knowledge` are disabled
  buttons naming the milestone that delivers them. Nothing is pretend-functional.
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
| Web unit | Vitest (jsdom) | API client, error mapping, connection indicator, card (no validity label), projects page (empty, list, load failure), event descriptions, event strip, stream hook (subscribe after the head, de-duplicate, reconnect, no retry on typed answers) |
| Browser | Playwright against a real API (`--ephemeral`) and the Vite dev server | first run and empty state, create/move/reorder/edit with reload, stale edit, keyboard use, disabled future views, backend loss and recovery, pushed updates, event strip, polling fallback, project switch, a real API process restarted under an open page, CLI and browser on the same state |

No fixtures or mocks live in application code; the GUI shows the real backend connection state.

## Security defaults

Loopback binding, CORS limited to the GUI origin, no secrets in fixtures or logs, no execution of
project code in M0. `NUMERICOS_DATA_DIR` is created on demand by `serve`/`db`; a project
`root_path` is validated as absolute, stored as a reference and never opened or executed before
the M3 supervisor defines a trust boundary.

## Deferred boundaries (documented, not built)

- **AgentAdapter** (M1): capabilities, session lifecycle, normalized events, `install_skills`;
  contract in `docs/AGENT_ADAPTER_CONTRACT.md`. Provider-specific IDs will live in an adapter
  mapping, never on Project/BoardCard. The ledger envelope above is the one the adapter events
  will reuse (`seq` is the contract's `sequence`); `research_id`, `run_id` and
  `agent_session_id` columns are added by batch migrations when M1/M3 need them.
- **SkillRegistry** (M1): `skill_id`, version or Git revision, `source_path`, SHA-256 content
  digest, compatibility flags, installation receipt; design in `docs/SKILL_ARCHITECTURE.md`.

## Known limitations of M0

- **Single user, single API process.** No authentication; the API binds to loopback. Live
  wake-ups need `uvicorn --workers 1`; another process writing to the database is seen by
  subscribers within one heartbeat.
- **No idempotency keys.** Updates are protected by optimistic locking (`version`); a retried
  `POST` creates a second record. Idempotency keys arrive with asynchronous submissions (M3-M5).
- **No delete or archive** for projects and cards, and no cross-project move of a card.
- **`root_path` is a stored reference.** It is validated as absolute, never opened or executed.
- **The list of projects is polled** every 5 seconds; only project pages have an event stream.
- **The event strip shows the 20 newest entries.** Older ones are read with
  `numericos events list` / `follow`. A full timeline view belongs to M3.
- **No drag and drop yet** (M1): cards move through their status select and up/down buttons.
- **Schema migrations need a manual restart** of a server started with `--reload`.
- **SQLite transactions serialise writers and readers** (`BEGIN IMMEDIATE`). Invisible for one
  local user; to be measured when the job supervisor writes telemetry in M3.

## Decisions

- ADR-0001: one Python distribution with module boundaries.
- ADR-0002: transactional event ledger, publish-after-commit, SQLite transaction policy and
  column renumbering.
- ADR-0003: Server-Sent Events as a replayable view of the ledger; cursor rules; the GUI uses
  the stream as a wake-up signal.
