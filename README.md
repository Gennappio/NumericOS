# NumericOS

NumericOS is a local-first agentic workbench for computational and numerical research: a
scientific board of typed objects, anchored discussions on agent answers, an approved-knowledge
context engine, and a runtime (NumericOS Runtime) that supervises real numerical experiments with
provenance, observability and validators. The GUI, the `numericos` CLI and external agents all
call the same API.

**Status:** pre-alpha. Milestone **M0** (foundations: persistent project board, API, CLI,
replayable event ledger) was accepted on 2026-10-12; the evidence is in
`docs/milestones/M0-gate.md`. The active milestone is **M3**, experiment engine, provenance and
numerical observability, which the project owner placed before M1 and M2
(`docs/adr/0004-observability-first.md`). So far M3 defines experiments by a contract, records
exactly which code, inputs and environment a run uses, and executes runs under a supervisor
that observes, bounds, cancels and recovers them. Scientific metrics, validators and the run
pages of the GUI are the next tickets: today a run shows what its process did, from the command
line and the API, and nothing yet says whether its result is valid.

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
make worker             # supervisor: executes queued runs (needed only to run experiments)
make web                # GUI on http://localhost:5173
make seed-demo          # optional: one clearly marked demo project (needs the API running)
```

Each command stays in the foreground: use one terminal per command.

`make api` applies pending schema migrations to `~/.numericos/numericos.db` before listening and
restarts itself when the Python source changes. `numericos db upgrade` / `db current` manage the
schema explicitly, and `numericos serve --ephemeral` starts the API on a throwaway data directory.

`make worker` also restarts itself when the source changes. Stopping or restarting a supervisor
never stops a run: every run has its own monitor process, and the next supervisor takes the run
over. Without a supervisor, runs stay queued.

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
5. **Recent events** below the board lists what the backend recorded, newest first, with who did
   it. Its indicator says whether updates are pushed live. Changes made from another tab or from
   the CLI appear on their own.

The indicator in the top right corner shows the real connection to the backend. If the API stops,
the GUI says so, marks what it shows as the last known state and disables every change.

## Running an experiment

An experiment is a contract file: what is asked, what varies, what stays fixed, how one run is
executed and within which limits. A run executes an exact commit of the project's Git
repository, exported for that run, so uncommitted edits are not part of it unless the contract
says `code: {mode: working_tree}`.

```yaml
# stability.yaml
schema: numericos.experiment.v1
question: Does reducing dt restore the stability of the explicit scheme?
independent_variables: {dt: [0.02, 0.01, 0.005]}
controls: {grid: 32, steps: 200}
execution:
  command: [python3, heat2d.py, --dt, "{dt}", --grid, "{grid}", --steps, "{steps}"]
limits: {wall_seconds: 300}
```

```bash
numericos project add "Heat 2D" --root-path /path/to/your/git/repository
numericos project trust PROJECT_ID          # allow commands to be executed in that directory
numericos experiment run stability.yaml -p PROJECT_ID -P dt=0.01
```

The last command registers the experiment, queues one run and follows it: the program's output
is printed as it arrives, each line with its arrival time and stream, and the exit code says
how the run ended (`0` succeeded, `10` failed, `11` cancelled, `12` timed out, `13` lost).
Afterwards, or from another terminal while it runs:

```bash
numericos run list -p PROJECT_ID            # newest runs of the project
numericos run show RUN_ID                   # status, exact code, exit, time, memory
numericos run logs RUN_ID -f                # output; -f follows until the run ends
numericos run resources RUN_ID --tail 5     # CPU and memory samples of the process tree
numericos run events RUN_ID                 # what happened to the run, in order
numericos run cancel RUN_ID                 # SIGTERM to the process group, SIGKILL after the grace period
numericos artifact list -r RUN_ID           # files the run left, with size and SHA-256
numericos run export RUN_ID                 # everything needed to repeat the run, as JSON
numericos worker list                       # is a supervisor alive?
```

A program finds its result directory in `$NUMERICOS_OUTPUT_DIR`; files it writes next to its
sources are listed with the results as well. `succeeded` means the program ended by itself with
exit code 0. It does not mean the result is valid.

A run gets a small environment: the supervisor's `PATH` without NumericOS's own Python
environment, plus what the contract declares (`execution.env`) or asks to inherit
(`execution.inherit_env`, the way to pass a secret). If your project has its own environment,
name its interpreter in the command, or create it in a build command:

```yaml
execution:
  build: [[uv, sync, --frozen]]
  command: [.venv/bin/python, heat2d.py, --dt, "{dt}"]
```

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
numericos events follow --project PROJECT_ID        # replay it, then follow live (Ctrl+C stops)
numericos seed-demo                                 # one clearly marked demo project
```

Exit codes: `0` success, `1` API error (envelope on stderr), `2` usage error, `3` API unreachable.
Commands that wait for a run end with how the run ended (`10` to `14`, see
`numericos run watch --help`).

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
src/numericos/   Python package: config, core, persistence (models, migrations), events, provenance,
                 executor (per-run monitor, supervisor), observability, services, api, cli
tests/           pytest suites (unit, persistence, provenance, executor, api, cli, integration);
                 `LiveServer` and `LiveWorker` run real API and supervisor subprocesses
contracts/       exported OpenAPI contract (generated, committed, drift-checked in CI)
apps/web/        React + TypeScript + Vite GUI; src/api/schema.d.ts is generated from contracts/
docs/            architecture.md, ADRs, milestone gate evidence, blueprint, skill and adapter docs
milestones/      executable development briefs M0-M5 (one ticket at a time)
skills/          canonical scientific Agent Skills (SKILL.md)
```

## Start here (contributors and coding agents)

1. `AGENTS.md`: product vision and project invariants.
2. `CURRENT_MILESTONE.md` and the brief it names (`milestones/M3/AGENTS.md`): the active tickets.
3. `docs/architecture.md`: what exists today and the decisions behind it (`docs/adr/`).
4. `docs/DEVELOPMENT_PACK.md`: the original development pack notes.
