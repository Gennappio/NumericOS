# NumericOS architecture (living document)

Status: **M0-T02** (model, migrations, unit of work, event ledger). Everything below describes
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
  events/                      ledger row builder, in-process wake-up notifier
  api/                         FastAPI app factory, routers, error envelope, correlation middleware
  cli/                         `numericos` command line (HTTP client; `serve`/`db` are server side)
tests/                         pytest: unit, persistence, api (TestClient), cli (real subprocess)
contracts/openapi.v1.json      exported public contract (generated, committed, drift-checked)
apps/web/                      React + TypeScript + Vite GUI (npm project)
  src/api/schema.d.ts          TypeScript types generated from contracts/openapi.v1.json
docs/, milestones/, skills/    specification pack (product invariants, briefs, canonical skills)
```

Dependency direction inside `src/numericos`: `core <- persistence <- events <- services <- api`;
`cli` only speaks HTTP. `services` and the data routes arrive with M0-T03.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `NUMERICOS_DATA_DIR` | `~/.numericos` | local-first directory; the database is `<data_dir>/numericos.db` |
| `NUMERICOS_HOST` | `127.0.0.1` | bind address; loopback by default, never exposed remotely |
| `NUMERICOS_PORT` | `8765` | API port |
| `NUMERICOS_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON list of browser origins |
| `NUMERICOS_API_URL` | `http://127.0.0.1:8765` | base URL used by the CLI |
| `VITE_API_URL` (web) | `http://127.0.0.1:8765` | API base URL baked into the GUI |

`numericos serve --ephemeral` uses a fresh temporary data directory (demos, e2e tests).

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
the durable commit, async subscribers (the SSE endpoint, T05) re-read the ledger by cursor. The
notifier carries no data, so delivery can never precede durability.

## Public API conventions

- Versioned prefix `/v1`; OpenAPI document at `/v1/openapi.json`, interactive docs at `/v1/docs`.
- `GET /v1/health` reports `status` (`ok` or `degraded`), `db` (`ok` or `unavailable`), the
  current and expected schema revision and the data directory. It always answers 200 while the
  process is alive; the fields say whether the database is usable.
- Every non-2xx response, including the framework's own 404/405/422/500, uses one envelope:

  ```json
  {"error": {"code": "NOT_FOUND", "message": "...", "details": {}, "correlation_id": "cor_..."}}
  ```

  Codes are stable UPPER_SNAKE identifiers. In use: `VALIDATION_ERROR` (422), `NOT_FOUND` (404),
  `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500). Planned by T03: `PROJECT_MISMATCH` (409),
  `STALE_REVISION` (409).
- `X-Correlation-ID`: accepted from the client when it matches `[A-Za-z0-9_.-]{1,64}`, otherwise a
  `cor_<ULID>` is generated; always echoed on the response and stored on every event.
- `X-Actor`: free label of the calling surface (`web:local`, `cli:local`, `cli:seed`); it is
  recorded, not trusted, on a loopback-only service.
- Request bodies reject unknown fields (`extra="forbid"`), so typos never silently no-op.
  Mutations require the record `version` (optimistic locking) from T03 on.
- Timestamps are UTC with a `Z` suffix. Neither IDs nor timestamps depend on the host timezone
  or locale (CI runs the tests under a non-UTC `TZ`).

## CLI conventions

`numericos` is an HTTP client of the API, never a second backend. Server-side commands are
limited to `serve` and `db upgrade|current`. With `--json`, stdout carries exactly one JSON
document and diagnostics go to stderr. Exit codes: `0` success, `1` API error (the envelope is
printed on stderr), `2` usage error, `3` API unreachable.

## Contracts pipeline

Pydantic models in `numericos.core.schemas` are the single source of the public schema:
`numericos openapi --output contracts/openapi.v1.json` exports it and `npm run gen:api` derives
`apps/web/src/api/schema.d.ts`. CI fails when either committed file is stale (`make check-contracts`).

## Testing layers

| Layer | Tool | Scope |
| --- | --- | --- |
| Unit | pytest | IDs, ordering, schemas, notifier |
| Persistence | pytest on a migrated temp SQLite | migrations (fresh, idempotent, round trip, `alembic check`), PRAGMAs, repositories, constraints, unit of work, publish-after-commit, sequence continuity across restarts |
| API | pytest + `TestClient` | routes, envelope, headers, CORS, health states |
| Process | pytest + `LiveServer` (real `numericos serve` subprocess) | CLI contract, startup migration, restart proofs (T05) |
| Web unit | Vitest (jsdom) | API client, components |
| Browser | Playwright against a real API (`--ephemeral`) and the Vite dev server | user journeys, empty and API-down states |

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

## Decisions

- ADR-0001: one Python distribution with module boundaries.
- ADR-0002: transactional event ledger, publish-after-commit, SQLite transaction policy and
  column renumbering.
