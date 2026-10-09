# M0 / AGENTS.md — Foundations, persistence, event backbone and first GUI

**Read `../../AGENTS.md` (repository root), `CURRENT_MILESTONE.md`, and `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md` first.** You are implementing **M0 only**. M0 must produce an actual application that can later support anchored agent discussions, experiment supervision and external calls. It must not pretend to perform science yet.

## 0. Why M0 exists

The research workspace will be both human-facing and agent-callable. We need a durable model that is independent of the browser/chat/client. A beautiful static dashboard without persistent objects/event replay would be a dead end. Equally, building a general distributed orchestration platform before the first project can be created would be wasted effort.

**Deliver a complete local vertical slice:** start the API + GUI, create a research project, add typed research cards, move/update a card, refresh/restart, see retained state, inspect the same objects with CLI/API, replay ordered events.

## 1. Exact scope

Implement:

- Reproducible single-repo development environment: Python backend, React/TypeScript frontend, shared public schema source; startup commands documented, sensible `.gitignore`, no automatic downloads of huge scientific models.
- FastAPI app, versioned `/v1` routes, CORS limited to local frontend origin; one consistent JSON error shape; Pydantic validation at public boundary.
- SQLite local DB, migrations (Alembic), local-first `data_dir` for DB and future artifacts; transactional writes; foreign keys enabled; WAL when appropriate; UTC timestamps.
- Minimum persistent entities: `Project`, `BoardCard`, `Event`. Reserve stable ID format and references for later entities but do not add empty tables prematurely.
- Typed BoardCard discriminator: `task | hypothesis | experiment | issue | decision`; `workflow_status`, `sort_order`, `title`, `description`, nullable `entity_ref`, `project_id`. Workflow examples: `backlog`, `planned`, `active`, `review`, `completed`, `blocked`. Do **not** encode truth as column membership.
- Event ledger with event ID, project ID, sequence, actor, subject ID, event type, UTC timestamp, schema version, payload, correlation ID. Event committed atomically with state change, SSE subscriber reads from ledger and replays by cursor/Last-Event-ID. Polling fallback acceptable in first tiny UI but SSE replay must be real.
- Minimal `numericos` CLI: `numericos serve`, `numericos project list --json`, `numericos project add ... --json` or equivalent typed client hitting same backend. Don't make CLI access SQLite separately.
- Functional responsive GUI: left project navigation, scientific Kanban board (basic cards allowed; full drag-drop in M1), detail/edit modal or panel, event/timeline strip, visible actual backend connection state; no hardcoded research results.
- API contract tests and basic browser smoke test. Seed demo projects only by explicit command and mark demo data clearly.

## 2. Suggested implementation layout

```text
apps/web/                         React, TS, Vite
apps/api/                         FastAPI app/routers + main
packages/core/                    Pydantic models/domain contracts
packages/persistence/             ORM mappings, migrations/repositories
packages/events/                  transactional event service + SSE cursor
packages/cli/                     Typer or argparse client
examples/heat2d-python/           reserved until M3
milestones/M0/AGENTS.md           this specification
```

Do not force packaging everything as installable components in M0. A smaller viable layout with explicit boundaries is preferred; record any deviation in `docs/architecture.md`.

## 2a. Forward compatibility without premature implementation

- The package/CLI identity is **NumericOS**, command `numericos`, not the old CRR command. Avoid a product name in persistent schema that prevents later renaming.
- Reserve only an explicit documented typed boundary `AgentAdapter` (not a full implementation); Codex App Server is the default M1 spike, subject to verified capabilities and ADR. Provider-specific IDs live in an adapter mapping, not in Project/BoardCard.
- Document future `SkillRegistry` entity ideas (skill_id, version, source_path, content_digest, compatibility/capability flags), but **do not** implement skill loading or agent execution in M0.
- Unit/API tests must be reproducible with no provider subscriptions, external API calls or models installed.

## 3. Required API (suggested routes)

```http
POST   /v1/projects
GET    /v1/projects
GET    /v1/projects/{project_id}
PATCH  /v1/projects/{project_id}
GET    /v1/projects/{project_id}/board
POST   /v1/projects/{project_id}/cards
PATCH  /v1/cards/{card_id}
GET    /v1/events?project_id=...&after=...    # ordered events or SSE
GET    /v1/health
```

API must return stable UUID/ULID IDs, UTC timestamps, revision/version for concurrency-sensitive records, and validation errors in machine-readable form. Consider optimistic locking for card moves (card version, no lost updates), but keep scope small. A card reorder request should state destination status and position; backend computes/stores a durable ordering. Default time and locale should not affect IDs.

Sample card representation (illustrative):

```json
{
  "id": "card-id",
  "project_id": "project-id",
  "type": "hypothesis",
  "title": "Sparse kernel cache locality",
  "workflow_status": "planned",
  "sort_order": 120,
  "entity_ref": null,
  "version": 3
}
```

## 4. UX acceptance, not just CRUD

- Scientific project is a dashboard: research question and project reference displayed prominently, typed cards visually distinguishable without implying validity/rating.
- User can add a hypothesis card with a title and move it between columns; reload and return to exact project retains it.
- A card shows type + workflow status; it **does not** display `supported/refuted` simply because moved to completed.
- Navigation anticipates later `Board`, `Experiments`, `Timeline`, `Agents`, `Knowledge`; unavailable views are either absent or clearly disabled, NEVER pretend-functional.
- Responsive layout at desktop and narrower widths; no horizontal unreadable truncation of important card text.
- Show useful empty/loading/error states and backend-unreachable warning. Never silently show stale mock state as real.
- Distinguish demo/mock values from recorded data (if fixtures are used).

## 5. Event-ledger reliability

- For a mutation, write updated object and event in **same DB transaction**; publish to SSE only after success.
- Cursor ordering comes from monotonically increasing DB sequence/event row ID; timestamps are display metadata, not ordering authority.
- SSE reconnect after disconnect emits missed events once by cursor; clients de-duplicate by event ID.
- Browser refresh does not lose board state. API process restart preserves DB and returns events.
- No broad polling loop that fabricates milestones or progress.
- Include correlation IDs now because M3+ link process events and agent actions across components.

## 6. Testing contract

Backend:
- Fresh DB migration upgrade, bootstrap and normal startup.
- Project CRUD and card update/reorder in real SQLite temp DB.
- Rollback test: invalid card update produces no event.
- Event publication: two events are replayed in sequence after client reconnect.
- Nonexistent IDs and wrong project membership return meaningful 404/409 rather than silent success.

Frontend:
- Create project via API (not mocked fetch) and card; move/update; reload; correct status/order displayed.
- Empty and API-down states.
- Accessibility basics: keyboard focus, labels and safe click targets.

CLI:
- `--json` stdout can be parsed by `json.loads`/jq; diagnostics go to stderr, non-zero exits on errors.
- CLI-created project appears in browser; browser-created project appears in CLI.

## 7. Work sequence / tickets (one at a time)

1. **M0-T01 — Repo/dev bootstrap:** Python and Node toolchains, dev scripts, lint/typecheck/test skeleton, start instructions; verify clean install.
2. **M0-T02 — Model and migrations:** Project, Card, Event; database transactions, sample repository tests.
3. **M0-T03 — Public API + CLI:** versioned API, response/error contracts, local client, integration tests.
4. **M0-T04 — Board UI:** project list, board, typed card add/update/move, real API data, browser tests.
5. **M0-T05 — Durable events and release gate:** transactional ledger, SSE cursor/replay, event strip, restart test, docs/ADR.

Finish each ticket with actual executed commands and results; never start T04 before T03 works.

## 8. Constraints / non-goals

**DO NOT:** integrate any live coding agent, create fake AI chats, implement comment anchoring, context compilation, numerical solvers, MLflow, Git worktree orchestration, background agents, workflow editors, remote multiuser auth, distributed execution or MCP. **Do** record `AgentAdapter` and `SkillRegistry` schema/interface sketches in docs without speculative implementations: M1 owns the real first provider integration and skill installation. Interfaces to later systems may be sketched in architecture docs, not built as speculative code. Do not create generic interfaces for concepts with only one unproven consumer.

Security default: bind to loopback, document project root path validation and risks of future arbitrary code execution. Do not put secrets in any fixtures or logs. Never silently auto-commit/merge the user's repository.

## 9. Evidence required for gate sign-off

- `README` exact commands: install, migrate, start API, start GUI, start CLI tests.
- Screenshot or real UI walkthrough describing create/move/reload, including no mocked data.
- Backend/frontend/CLI test commands and PASS/FAIL; DB/API restart proof.
- Verified event IDs/cursors and SSE reconnect behavior.
- Documented schema/API and outstanding known limitations.
- One coherent reviewable commit; no claim that future milestones already work.

**Exit gate:** a scientist can create and organize a real computational project, and an external scripted client sees the same durable state and ordered events.
