# NumericOS

NumericOS is a local-first agentic workbench for computational and numerical research: a
scientific board of typed objects, anchored discussions on agent answers, an approved-knowledge
context engine, and a runtime (NumericOS Runtime) that supervises real numerical experiments with
provenance, observability and validators. The GUI, the `numericos` CLI and external agents all
call the same API.

**Status:** pre-alpha. Milestone **M0** (foundations: persistent project board, API, CLI,
replayable event ledger) was accepted on 2026-10-12; the evidence is in
`docs/milestones/M0-gate.md`. **M3** (experiment engine, provenance, numerical observability)
was built next by the owner's earlier decision (`docs/adr/0004-observability-first.md`) and is
paused after its fourth ticket: experiments are defined by a contract, a run records exactly
which code, inputs and environment it uses, a supervisor executes, observes, bounds, cancels and
recovers runs, scientific metrics are collected with explicit guardrails, and the GUI follows
every run live. Validators do not exist yet: nothing says whether a result is valid.

The active work is **M1 in the owner's version** (`docs/adr/0008-owner-redirection-commentable-agent-documents.md`):
conversations with the coding agent inside a project, answers and documents that can be
commented and sent back to the agent, the theory of the project as a paper, descriptions of
its files and of its execution, the plan as a board. The first ticket is done: a project has
**conversations with Claude Code**, held from the GUI or the command line and executed by the
supervisor, with every action of the agent, every file it changed, what its permission mode
refused and what the turn cost on record.

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

1. **New project**: give it a name, the research question and, to run experiments, the absolute
   path of the project's Git repository.
2. On the project page use **New card** (or the `+` of a column) to add typed cards: task,
   hypothesis, experiment, issue, decision.
3. Move a card with its status select (to another column) or its up/down buttons (inside the
   column); click its title to edit it. Reload the page or restart `make api`: the board is
   exactly as you left it.
4. Columns are workflow status only. Nothing on the board states whether a result is valid.
5. **Recent events** below the board lists what the backend recorded, newest first, with who did
   it. Its indicator says whether updates are pushed live. Changes made from another tab or from
   the CLI appear on their own.

6. **Experiments** (the second tab of a project) needs `make worker` as well. It shows whether
   execution is allowed in the project directory and whether a supervisor is alive. Allow
   execution, then register a contract found in the repository with one click (or paste one).
   For a first try, make this checkout the project's code path and register
   `examples/heat2d-python/experiment.yaml`.
7. On an **experiment**, read its contract in words, choose a value for each variable and queue
   a run. Its runs are listed side by side with the last value of every declared metric.
8. A **run page** follows the run while it goes on: how its process stands, how far the
   observation reaches (process, parsers, instrumentation, validators), a chart per metric
   with the bounds of the contract, CPU and memory of the process tree, the output on request,
   exactly what ran, what happened to it and the files it left. A run that is going on can be
   stopped from there; a run of an exact commit can be run again.

9. **Agent** (the third tab) talks to Claude Code about the project. It needs the `claude`
   command installed and logged in, the project directory allowed for execution (the agent
   reads, edits and runs the code as you) and `make worker`. Start a conversation, choose what
   the agent may do (read only; edit files; full autonomy, as with every permission skipped in a
   terminal) and ask. The prompt is recorded at once; the answer arrives as a turn: first the
   agent's actions as they happen (the file read, the command run, whether it succeeded), then
   the answer with its mathematics rendered, its model, its cost and its duration. What the
   mode refused is listed on the answer. A turn can be stopped. Every turn is a call on your
   Claude account.

The indicator in the top right corner shows the real connection to the backend. If the API stops,
the GUI says so, marks what it shows as the last known state and disables every change.

A run that ended normally is labelled "Ended normally", not "passed": that is a statement about
the process. Until validators exist, every run page says that nothing has judged the result.

## Running an experiment

An experiment is a contract file: what is asked, what varies, what stays fixed, how one run is
executed, which metrics are measured and by whom, which bounds stop a run, and within which
limits. A run executes an exact commit of the project's Git repository, exported for that run,
so uncommitted edits are not part of it unless the contract says `code: {mode: working_tree}`.

This repository ships two worked experiments. `examples/heat2d-python` is the explicit scheme
for the 2D heat equation with time steps on both sides of its stability limit; it needs only
`python3`. With `make api` and `make worker` running, from the top of the checkout:

```bash
numericos project add "Heat 2D" --root-path "$PWD"
numericos project trust PROJECT_ID          # allow commands to be executed in that directory
numericos experiment run examples/heat2d-python/experiment.yaml -p PROJECT_ID -P dt=0.0002
numericos experiment run examples/heat2d-python/experiment.yaml -p PROJECT_ID -P dt=0.0003
```

Each command registers the experiment (once), queues one run and follows it: the program's
output is printed as it arrives, each line with its arrival time and stream, and the exit code
says how the run ended (`0` succeeded, `10` failed, `11` cancelled, `12` timed out, `13`
lost). The first run is stable and ends `succeeded`. The second is above the stability limit:
a guardrail of the contract stops it and it ends `failed` with the class
`numerical_instability`, keeping its series as evidence. Both take a fraction of a second;
`experiment-fine.yaml` in the same directory runs for about twelve seconds, long enough to
watch. The reasoning behind the time steps and the guardrail is in
`examples/heat2d-python/README.md`; `examples/sparse-cg-cpp` is a C++ solver that exits
normally without the accuracy it reports.

Afterwards, or from another terminal while a run is in progress:

```bash
numericos run list -p PROJECT_ID            # newest runs of the project
numericos run show RUN_ID                   # status, exact code, exit, time, memory
numericos run metrics RUN_ID                # coverage per level, every series, diagnostics
numericos run metric RUN_ID l2_error -f     # the samples of one metric, following the run
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

To make your own solver observable, print one JSON line per value
(`{"schema": "numericos.metric.v1", "name": "residual", "value": 3.2e-4, "step": 42}`) or let
the contract read numbers from the output it already prints: `docs/instrumentation.md`.

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
numericos agent capabilities                        # is the claude command found?
numericos agent ask -p PROJECT_ID "What does this solver compute?"   # new conversation, waits
numericos agent ask -s SESSION_ID "And its stability condition?"     # continues it
numericos agent sessions -p PROJECT_ID              # the conversations of a project
numericos agent show MESSAGE_ID                     # one answer with every action of the agent
numericos agent cancel MESSAGE_ID                   # stop a turn
```

Exit codes: `0` success, `1` API error (envelope on stderr), `2` usage error, `3` API unreachable.
Commands that wait for a run end with how the run ended (`10` to `14`, see
`numericos run watch --help`); `agent ask` ends with how the turn ended (`0` answered, `10`
failed, `11` stopped, `13` interrupted, `14` still going after `--timeout`).

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
| `NUMERICOS_CLAUDE_COMMAND` | `["claude"]` (JSON list; the tests point it at `tests/fake_claude.py`) |
| `NUMERICOS_AGENT_MAX_BUDGET_USD` | `5` per turn |
| `NUMERICOS_AGENT_MAX_PARALLEL` | `2` turns at a time per supervisor |

## Layout

```text
src/numericos/   Python package: config, core, persistence (models, migrations), events, provenance,
                 executor (per-run monitor, supervisor), agents (Claude Code adapter, turns),
                 observability, services, api, cli
tests/           pytest suites (unit, persistence, provenance, executor, api, cli, integration);
                 `LiveServer` and `LiveWorker` run real API and supervisor subprocesses
contracts/       exported OpenAPI contract (generated, committed, drift-checked in CI)
apps/web/        React + TypeScript + Vite GUI; src/api/schema.d.ts is generated from contracts/
examples/        worked experiments with their contracts: heat2d-python, sparse-cg-cpp
docs/            architecture.md, instrumentation.md, ADRs, milestone gate evidence, blueprint,
                 skill and adapter docs
milestones/      executable development briefs M0-M5 (one ticket at a time)
skills/          canonical scientific Agent Skills (SKILL.md)
```

## Start here (contributors and coding agents)

1. `AGENTS.md`: product vision and project invariants.
2. `CURRENT_MILESTONE.md` and what it names (ADR-0008, `milestones/M1/AGENTS.md`): the active
   tickets, in the owner's order.
3. `docs/architecture.md`: what exists today and the decisions behind it (`docs/adr/`).
4. `docs/DEVELOPMENT_PACK.md`: the original development pack notes.
