# NumericOS architecture (living document)

Status: **M0-T01** (repo and dev bootstrap). Everything below describes what exists; later
milestones extend this file instead of replacing it. Roadmap and acceptance gates live in
`docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md` and `milestones/`.

## Repository layout

```text
pyproject.toml, uv.lock        Python distribution "numericos" (see ADR-0001)
src/numericos/
  config.py                    Settings (NUMERICOS_* environment variables)
  core/                        public schemas (Pydantic), typed IDs, typed errors
  api/                         FastAPI app factory, routers, error envelope, correlation middleware
  cli/                         `numericos` command line (HTTP client of the API)
tests/                         pytest: in-process TestClient + real API subprocess (LiveServer)
contracts/openapi.v1.json      exported public contract (generated, committed, drift-checked)
apps/web/                      React + TypeScript + Vite GUI (npm project)
  src/api/schema.d.ts          TypeScript types generated from contracts/openapi.v1.json
docs/, milestones/, skills/    specification pack (product invariants, briefs, canonical skills)
```

Dependency direction inside `src/numericos`: `core <- persistence <- events <- services <- api`;
`cli` only speaks HTTP. `persistence`, `events` and `services` arrive with M0-T02/T03.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `NUMERICOS_DATA_DIR` | `~/.numericos` | local-first directory for the database and artifacts |
| `NUMERICOS_HOST` | `127.0.0.1` | bind address; loopback by default, never exposed remotely |
| `NUMERICOS_PORT` | `8765` | API port |
| `NUMERICOS_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON list of browser origins |
| `NUMERICOS_API_URL` | `http://127.0.0.1:8765` | base URL used by the CLI |
| `VITE_API_URL` (web) | `http://127.0.0.1:8765` | API base URL baked into the GUI |

`numericos serve --ephemeral` uses a fresh temporary data directory (demos, e2e tests).

Tooling: `uv` manages the Python environment in `./.venv`; the Makefile and the Playwright config
export `UV_PROJECT_ENVIRONMENT` explicitly because a global value in the developer's shell would
otherwise redirect `uv sync` into an unrelated environment.

## Public API conventions

- Versioned prefix `/v1`; OpenAPI document at `/v1/openapi.json`, interactive docs at `/v1/docs`.
- Every non-2xx response, including the framework's own 404/405/422/500, uses one envelope:

  ```json
  {"error": {"code": "NOT_FOUND", "message": "...", "details": {}, "correlation_id": "cor_..."}}
  ```

  Codes are stable UPPER_SNAKE identifiers. In use: `VALIDATION_ERROR` (422), `NOT_FOUND` (404),
  `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500). Planned by later tickets:
  `PROJECT_MISMATCH` (409), `STALE_REVISION` (409), `DB_UNAVAILABLE` (503).
- `X-Correlation-ID`: accepted from the client when it matches `[A-Za-z0-9_.-]{1,64}`, otherwise a
  `cor_<ULID>` is generated; always echoed on the response and stored on events (from T02).
- `X-Actor`: free label of the calling surface (`web:local`, `cli:local`, `cli:seed`); it is
  recorded, not trusted, on a loopback-only service.
- Request bodies reject unknown fields (`extra="forbid"`), so typos never silently no-op.
- IDs are `<prefix>_<ULID>` strings (`prj_`, `card_`, `evt_`, `cor_`); timestamps are UTC with a
  `Z` suffix. Neither depends on the host timezone or locale (CI runs the tests under a non-UTC
  `TZ`).

## CLI conventions

`numericos` is an HTTP client of the API, never a second backend. Server-side commands are limited
to `serve` (and `db upgrade|current` from T02). With `--json`, stdout carries exactly one JSON
document and diagnostics go to stderr. Exit codes: `0` success, `1` API error (the envelope is
printed on stderr), `2` usage error, `3` API unreachable.

## Contracts pipeline

Pydantic models in `numericos.core.schemas` are the single source of the public schema:
`numericos openapi --output contracts/openapi.v1.json` exports it and `npm run gen:api` derives
`apps/web/src/api/schema.d.ts`. CI fails when either committed file is stale (`make check-contracts`).

## Testing layers

| Layer | Tool | Scope |
| --- | --- | --- |
| API | pytest + `TestClient` | routes, envelope, headers, CORS |
| Process | pytest + `LiveServer` (real `numericos serve` subprocess) | CLI contract, restart proofs (T05) |
| Web unit | Vitest (jsdom) | API client, components |
| Browser | Playwright against a real API (`--ephemeral`) and the Vite dev server | user journeys, empty and API-down states |

No fixtures or mocks live in application code; the GUI shows the real backend connection state.

## Security defaults

Loopback binding, CORS limited to the GUI origin, no secrets in fixtures or logs, no execution of
project code in M0. `NUMERICOS_DATA_DIR` is created on demand; a project `root_path` (T02) is
stored as a reference and never opened or executed before the M3 supervisor defines a trust
boundary.

## Deferred boundaries (documented, not built)

- **AgentAdapter** (M1): capabilities, session lifecycle, normalized events, `install_skills`;
  contract in `docs/AGENT_ADAPTER_CONTRACT.md`. Provider-specific IDs will live in an adapter
  mapping, never on Project/BoardCard.
- **SkillRegistry** (M1): `skill_id`, version or Git revision, `source_path`, SHA-256 content
  digest, compatibility flags, installation receipt; design in `docs/SKILL_ARCHITECTURE.md`.
- Reserved ID prefixes for later entities are listed in `numericos/core/ids.py`.

## Decisions

- ADR-0001: one Python distribution with module boundaries (this layout).
