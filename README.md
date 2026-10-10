# NumericOS

NumericOS is a local-first agentic workbench for computational and numerical research: a
scientific board of typed objects, anchored discussions on agent answers, an approved-knowledge
context engine, and a runtime (NumericOS Runtime) that supervises real numerical experiments with
provenance, observability and validators. The GUI, the `numericos` CLI and external agents all
call the same API.

**Status:** pre-alpha, milestone **M0** (foundations) in progress; see `CURRENT_MILESTONE.md`.
Nothing here performs science yet: M0 delivers the persistent project board, the API, the CLI and
the event ledger that later milestones build on.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ and npm
- Playwright Chromium for browser tests (installed by `make install`)

## Install

```bash
git clone https://github.com/Gennappio/NumericOS.git
cd NumericOS
make install            # uv sync + npm ci + playwright install chromium
```

## Run

```bash
make api                # API on http://127.0.0.1:8765 (health: /v1/health, docs: /v1/docs)
make web                # GUI on http://localhost:5173
make seed-demo          # optional: one clearly marked demo project (needs the API running)
```

`make api` applies pending schema migrations to `~/.numericos/numericos.db` before listening and
restarts itself when the Python source changes. `numericos db upgrade` / `db current` manage the
schema explicitly, and `numericos serve --ephemeral` starts the API on a throwaway data directory.

## Using the GUI

Open http://localhost:5173 with the API running.

1. **New project**: give it a name, the research question and, optionally, the absolute path of
   the research code (stored as a reference only).
2. On the project page use **New card** (or the `+` of a column) to add typed cards: task,
   hypothesis, experiment, issue, decision.
3. Move a card with its status select (to another column) or its up/down buttons (inside the
   column); click its title to edit it. Reload the page or restart `make api`: the board is
   exactly as you left it.
4. Columns are workflow status only. Nothing on the board states whether a result is valid.

The indicator in the top right corner shows the real connection to the backend. If the API stops,
the GUI says so, marks what it shows as the last known state and disables every change.

## Command line

The `numericos` CLI is a client of the same API the GUI uses (`.venv/bin/numericos` after
`make install`). Add `--json` to any command for machine-readable output on stdout.

```bash
numericos project add "Heat 2D" --question "Is the explicit scheme stable at dt = 0.01?"
numericos project list
numericos card add --project PROJECT_ID --type hypothesis --title "H01: ..."
numericos card move CARD_ID --status review --position 0
numericos card list --project PROJECT_ID
numericos events list --project PROJECT_ID          # the ordered event ledger
numericos seed-demo                                 # one clearly marked demo project
```

Exit codes: `0` success, `1` API error (envelope on stderr), `2` usage error, `3` API unreachable.

The Makefile pins the Python environment to `./.venv` (it exports `UV_PROJECT_ENVIRONMENT`), so a
global `UV_PROJECT_ENVIRONMENT` in your shell never redirects NumericOS dependencies into another
project's environment. When calling `uv` directly, do the same: `UV_PROJECT_ENVIRONMENT=.venv uv run ...`.

## Test and quality

```bash
make test               # pytest (API + real subprocess + CLI) and vitest
make lint               # ruff check/format, eslint
make typecheck          # mypy --strict, tsc
make e2e                # Playwright against a real API process (own ports and data directory)
make check-contracts    # regenerate contracts/openapi.v1.json + TS types, fail if stale
```

## Configuration

| Variable | Default |
| --- | --- |
| `NUMERICOS_DATA_DIR` | `~/.numericos` |
| `NUMERICOS_HOST` / `NUMERICOS_PORT` | `127.0.0.1` / `8765` |
| `NUMERICOS_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` |
| `NUMERICOS_API_URL` (CLI) | `http://127.0.0.1:8765` |
| `VITE_API_URL` (GUI) | `http://127.0.0.1:8765` |

## Layout

```text
src/numericos/   Python package: config, core, persistence (models, migrations), events, services, api, cli
tests/           pytest suites (unit, persistence, api, cli, integration); `LiveServer` runs a real API subprocess
contracts/       exported OpenAPI contract (generated, committed, drift-checked in CI)
apps/web/        React + TypeScript + Vite GUI; src/api/schema.d.ts is generated from contracts/
docs/            architecture.md, ADRs, blueprint, skill architecture, adapter contract
milestones/      executable development briefs M0-M5 (one ticket at a time)
skills/          canonical scientific Agent Skills (SKILL.md)
```

## Start here (contributors and coding agents)

1. `AGENTS.md`: product vision and project invariants.
2. `CURRENT_MILESTONE.md` and `milestones/M0/AGENTS.md`: the active brief and its tickets.
3. `docs/architecture.md`: what exists today and the decisions behind it (`docs/adr/`).
4. `docs/DEVELOPMENT_PACK.md`: the original development pack notes.
