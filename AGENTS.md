# AGENTS.md — NumericOS | Agentic Computational Research Workbench

> Repository-wide instructions. **Read this file, `CURRENT_MILESTONE.md` and the corresponding `milestones/Mx/AGENTS.md` before changing code.** The milestone files are executable development briefs, not instructions for an existing application. Do not claim that described APIs, CLI commands, jobs or features exist until implemented and tested.

## 1. Product vision — what we are building

**NumericOS** (product name) is a **local-first agentic workbench for computational and numerical research**, with a dedicated **NumericOS Runtime** (internal engine). It helps humans and external agent systems conduct, observe, question, revise and reproduce numerical/computational research. Domains include numerical PDEs, CFD, FEM, sparse linear algebra, optimization, statistical computing, scientific ML, bioinformatics and stochastic/agent-based simulation. NumericOS is not an ML-only application.

NumericOS consists of three cooperating products:

1. **Research Workspace / Cockpit**: a scientific Trello-like board of typed objects; navigable project history; research timeline; an experiment explorer; metric plots; resource/job view; and an agent activity view. The GUI is central to the product, NOT a decorative dashboard tacked on at the end.
2. **Anchored Discussions + Knowledge/Context Engine**: ordinary assistant answers remain readable Markdown; users can freely select an arbitrary substring and choose **Ask / Suggest Change / Add Note**. Each selection produces a persistent, anchored, local thread. Changes are proposed as diff; only an explicit user action edits/revises content or promotes approved knowledge. The context compiler feeds applicable approved constraints, decisions, evidence and unresolved questions to new agent sessions without blindly replaying the full chat.
3. **NumericOS Runtime**: scientific hypotheses/experiments/runs as typed entities; Git and input provenance; durable job supervision; numerical and system observability; evidence-based validators; bounded autonomous research loops; scientific skills; optional multiagent delegation. CLI, API and GUI call the SAME runtime. The runtime may be invoked by external agents (CLI first; Python/HTTP native; MCP/A2A optional).

**Differentiator**: general coding agents present research as sequences of chat turns and tool calls. NumericOS presents it as linked hypotheses, experiments, numerical observations, evidence, corrections, decisions and reproducible research context.

## 2. Product behavior that must survive every refactor

- **Text selection first, not forced atomization:** do not require the LLM to split each answer into artificial cards. Users select any span of the rendered text. The selected span stays visible with a stable highlight and sidebar thread; the parent response stays in place. Code, maths and repeated substrings require careful anchoring or explicit unsupported states.
- **No conversation wall:** focused questions use a local thread. Never automatically inject that thread's transcript into the primary coding-agent conversation; the user can explicitly choose to continue/promote a clarified conclusion. Prefer concise focused responses and expandable details.
- **Correction != endorsement != source edit != code change:** user annotation, suggestion, accepted text revision, approved knowledge item, and implementation task are five distinct operations. No silent propagation.
- **Board workflow status != scientific validity:** a completed experiment may be inconclusive, and a refuted hypothesis may still be historically valuable. Keep operational Kanban status separate from epistemic status.
- **Observability is an execution property:** logs, metrics, process state, provenance and agent decision events are recorded as the job runs, not reconstructed by LLM prose afterwards. A missing instrument is explicitly visible.
- **Scientific method rather than metric chasing:** formulate testable hypotheses, expected effects, controlled variables, measurements, falsification/decision criteria and scientific conclusions. Keep exploratory search distinct from confirmatory evaluation.
- **Lean code, rigorous numerics:** do not write hyper-defensive or enterprise-framework code around an experimental solver. Avoid catch-all exceptions, redundant retries, unnecessary fallbacks, invented configuration layers, over-generalization. Retain boundary/API safety, fail-fast invariants, numerical correctness, resource limits and scientific validity gates.
- **Provider-agnostic agent execution:** use a versioned `AgentAdapter` contract and capability negotiation. First integrated adapter: **Codex App Server**, with **Claude Agent SDK and Pi RPC** as first-class planned adapters (sequence may be changed after an M1 feasibility spike and documented ADR). Never assume agent feature parity. Do not force a particular provider, model, authentication mechanism or MCP.
- **Canonical scientific skill registry from M1:** one project-owned Agent Skills collection (`skills/<name>/SKILL.md`), not separate provider-authored prompts. Install/discover via provider adapters; record exact skill IDs, versions and content hashes. Skill instructions are not runtime guarantees: mandatory checks belong to deterministic validators and the NumericOS Runtime.
- **Progressive skill loading:** only skills applicable to the delegated objective should be activated; avoid bloated system prompts and redundant tool instructions.
- **Evidence travels across systems:** external agents receive typed results, exact artifact links, explicit limitations and correlated traces — not thousands of log lines or chat dumps.

## 3. Architectural boundaries

```text
  NumericOS GUI (React)       numericos CLI / SDK       External research agents
            |                      |                          |
            +----------------------+--------------------------+
                                   |
                         NumericOS API + SSE
                                   |
                 Persistent domain/event/knowledge store
                         |                     |
                Context + Skills        Research Controller
                         |                     |
                  AgentAdapter           Job Supervisor
                    |  |  |                 |
               Codex Claude Pi      Local / Docker / SLURM
```

- Canonical workflow state: DB + transactional append-only event ledger; event published only after commit. SSE is a view/replay transport, not truth.
- Code history: Git. Baselines immutable; full executed SHA plus dirty/diff digest when applicable, never only branch names.
- Data/weights/results: files/artifact store with identifiers/checksums; don't commit scientific bulk data to Git.
- Agent chat: immutable message versions; derived annotations and threads never overwrite messages.
- Scientific objects: Project, BoardCard, Hypothesis, Experiment, Run, Metric, Validation, Evidence, Decision, KnowledgeItem, ContextSnapshot, AgentSession, Annotation, Thread, Event, Artifact. Introduce persistence incrementally, maintain stable IDs.
- Persisted run state belongs to a **long-lived supervisor/worker** independent of CLI/web request lifetime. Reconnect/restart semantics must be proven, not assumed.
- Only explicitly delegated sub-research belongs to NumericOS; any parent research orchestrator retains ownership of the overall research goal.

## 4. Tech choices and scope discipline

- Frontend: React + TypeScript + Vite, Tailwind/shadcn/ui as useful; dnd-kit for Kanban; React Flow only when needed; chart library for real time series; read-only Markdown renderer with separate robust text anchors; BlockNote only if a real editable document workflow warrants it.
- Backend: Python 3.12+ with FastAPI, Pydantic, SQLAlchemy/Alembic and SQLite WAL. PostgreSQL only after scaling needs arise.
- Agent providers: first M1 vertical slice uses **Codex App Server** with structured events; follow with **Claude Agent SDK**, **Pi RPC** and optional OpenCode adapter. The order is revisable after a feasibility spike. Use structured protocols, explicit session and approval lifecycles; never parse ANSI terminal chat as stable API. Provider auth/licensing are different and must be checked before shipping commercially.
- Agent adapter API: `capabilities`, `start`, `prompt`, `stream_events`, `interrupt`, `resume` (if supported), `close`, `install_skills`. Normalize events, errors, approvals and tool statuses; mark unsupported capabilities honestly. Use test fakes only for contract/unit tests, not as substitute for a real M1 integration.
- Execution: subprocess/process groups/psutil first; SLURM, Docker, distributed schedulers later. SSE for durable streamed updates; only use WebSocket if a real bidirectional requirement materializes.
- Scientific skill library: canonical [Agent Skills](https://agentskills.io/specification) (`SKILL.md` with metadata and optional scripts/references). **M1** includes registry, install/discovery, explicit selection and minimal `scientific-method`, `research-code-style`, `numerical-validation` instructions; **M3** adds executable checks/observability bindings; **M4** adds domain-specific skill suites, task-based selection and evaluated research-loop skill. Scientific skills guide the agent; deterministic validators determine pass/fail. See `docs/SKILL_ARCHITECTURE.md`.
- Use libraries instead of recreating editor frameworks, tracing standards, Git, numerical kernels or general coding-agent inference.
- Default deployment local and loopback-bound. No unsafe remote execution of arbitrary code. Secrets and sensitive data excluded/redacted from LLM inputs, telemetry and persisted logs; explicit trust boundary for agent-generated code.

## 5. User journeys to preserve

**Journey A — Science + discussion:** user opens numerical project → sees scientific board → asks agent for analysis → highlights arbitrary phrase in assistant response → Ask opens sidebar micro-thread → optional Suggest Change shows local diff → Accept creates new immutable response revision → Promote creates versioned reviewed knowledge → fresh agent sees only applicable approved context and references, not giant old chat.

**Journey B — Computation + evidence:** create baseline → formulate H01 with controls/prediction/falsification → agent makes isolated minimal code change → supervisor executes observed run → numerical signals, resource usage, code/input versions recorded → validator compares candidate against baseline → board, explorer and timeline show evidence → no automatic merge.

**Journey C — External delegation:** parent agent invokes `numericos research submit … --json` or API → receives ID promptly → disconnects → durable NumericOS supervisor manages process independently → parent later observes state/events/results → evidence and next-step recommendations are machine-readable → optional second agent is isolated.

## 6. Contract design conventions

- Public API versioned (`/v1`), stable machine-readable error codes, idempotency key on submissions and mutating commands where needed.
- IDs distinguish `project_id`, `hypothesis_id`, `experiment_id`, `run_id`, `research_id`, `agent_session_id`, `message_id`, `annotation_id`, `context_snapshot_id`.
- Every trace/event includes event ID, UTC timestamp, project/research/run correlation, type, severity, producer and immutable reference to supporting evidence when present.
- Project/context access scoped: agent gets only approved knowledge for its current task plus explicitly requested open questions; keep provenance and a context digest; expose `Why included?` inspection in UI.
- Serializations (`--json`, HTTP and event envelopes) have shared schema and documented version; STDOUT contains parseable machine output, diagnostics on STDERR. Do not provide conflicting GUI/CLI interpretations.
- Refuse silent reattachment of ambiguous text highlights; mark `ambiguous` or `orphaned` and ask user to repair.
- `DONE` and scientific `SUPPORTED` are NOT synonyms; model separately.

## 7. Method of implementation (every milestone)

1. Read entire ACTIVE milestone file and existing code/ADR/contracts; do NOT proceed to other milestones merely because they are described.
2. Identify a small observable vertical slice, explicit dependency boundaries, and tests before coding. For changes of public schema or workflow, write/refresh an architecture decision record.
3. Inspect current capabilities/official libraries and reuse; prefer straightforward implementation, not speculative abstractions.
4. Implement backend, UI, persistence and tests that make the slice truly work. Use real execution, no fake 'live' metrics or pretend AI responses.
5. Verify the actual user journey including reload/restart, edge cases, errors, provenance. For UI use real browser interaction tests where feasible; review screenshots for layout/regressions.
6. Make an atomic Git commit after verified milestones or independently reviewable tasks; record tests and limitations. No destructive cleanup of user's work.
7. Produce a concise handoff: implemented behavior, changed files, commands/tests and results, open issues, next ticket. No monolithic narrative or unsupported claims.

## 8. Cross-milestone gates

- M0: database + API + SSE + GUI/CLI project CRUD really persistent.
- M1: real provider-integrated agent session (Codex first unless documented alternative), scientific board, **arbitrary selection anchored** Ask/Suggest/Note, local threads preserved without polluting main chat, and **working scientific skill registry/install/selection** visible in GUI.
- M2: explicit knowledge approval + deterministic context snapshots; fresh agent follows revised approved constraint and can inspect provenance.
- M3: actual numerical run + live-observed metrics + Git provenance + baseline comparison + persistent supervisor semantics; log exact selected skill versions/hashes and run real numeric validators independent of the LLM.
- M4: bounded research plan proposes/tests/evaluates multiple hypotheses, automatic but reviewable skill selection, domain overlays, scientific validation, budget/approval gates and reversible unmerged changes.
- M5: external agent invokes asynchronous NumericOS job and later queries results; multiple agents/projects isolated; optionally HPC/MCP/A2A/editor graph.

## 9. Validation across releases

Use fixed benchmark tasks (2D diffusion CFL violation, wrong PDE boundary, sparse compute performance and accuracy, stochastic ABM reproducibility). Compare **A** a chosen coding agent with no NumericOS skills, **B** the *same agent and model* + selected scientific skills/tools, **C** B + NumericOS runtime under matched model/compute/token budgets. Separately compare chat-only workflow vs anchored-discussion/board UI for decision-retrieval, accidental instruction loss, task continuation in fresh session. Independent executable graders, repeated runs, documented uncertainties. Never attribute an improvement to NumericOS without an ablation of its components.

## 10. Do-not-build list (until justified)

New generic foundation agent, giant arbitrary-agent graph engine, multi-tenant SaaS, self-hosted inference platform, universal C++/Python instrumentation, automatic scientific truth validator, full IDE/editor or bespoke visualization library, speculative adapters for unneeded protocols.

## 11. Source documents and precedence

1. **This root file:** project invariants, product vision.
2. **`CURRENT_MILESTONE.md` + `milestones/Mx/AGENTS.md`:** detailed current scope, tests, tasks and acceptance gates.
3. `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md`: updated milestone roadmap and acceptance criteria.
4. `docs/SKILL_ARCHITECTURE.md`: canonical skills, adapter installation, reproducibility and phase-specific gates.
5. `docs/AGENT_ADAPTER_CONTRACT.md`: provider-independent capability/event contracts and provider smoke tests.
6. `docs/ml-autopilot-reference_SKILL.md`: original ML-specific worktree/monitoring/provenance procedure; adapt to numerical domains without forcing ML assumptions on PDE/FEM/ABM.

**IMPORTANT:** A milestone `AGENTS.md` stored under `milestones/Mx/` is not automatically in the ancestor path of source files under `apps/` or `packages/`. The developer agent MUST explicitly read it at session start, as instructed here. Only set the current milestone pointer after the previous milestone has passed acceptance tests.
