# NumericOS — Implementation Blueprint v0.2

**Status:** implementation plan, not a claim that code exists. **Product:** NumericOS — agentic computational research workbench. **Internal engine:** NumericOS Runtime. **Canonical CLI name (proposed):** `numericos`.

## 0. The problem, the intended product and the non-goal

Today numerical researchers using general coding agents must navigate long conversations, scattered commits, raw terminal output and poorly contextualized experiments. NumericOS should make *scientific research* rather than chat history the central object. It is local-first, with a visual Research Workspace and a programmatically callable runtime for other agent systems.

Primary user journeys:

1. **Read/discuss:** ask an agent about a solver, select any arbitrary text in the rendered answer and choose **Ask / Suggest Change / Add Note**. A short sidebar thread addresses that exact span; acceptance makes a versioned revision, whereas explicit approval promotes a scoped project decision. The main answer remains visible.
2. **Organize:** scientific Trello-like board with typed cards and workflow state; evidence/epistemic state independent of card status. Timeline and experiment graph show what happened and why.
3. **Compute:** define hypothesis, prediction, controlled variables, falsification, metrics and a protocol; run isolated numerical experiments with Git, resources, input and environment provenance. Observe real signals while processes run, use versioned numerical validators and compare against baseline.
4. **Automate:** bounded research loops with budget, pause/restart, concise event dossiers, human approval at designated gates. Agent role and activated skills can be chosen per step.
5. **Delegate:** a parent scientific agent calls NumericOS through native CLI/API, receives a job ID immediately and later retrieves typed evidence, without needing MCP or access to internal chat transcripts.

**Non-goal:** a brand-new generic foundation coding agent, an IDE clone, universal numerical correctness proof or fully autonomous scientific discovery platform in v0.2.

## 1. Architecture and ownership

```text
   NumericOS GUI (React)       Native CLI/Python SDK       Parent agent/orchestrator
             |                        |                           |
             +------------------------+---------------------------+
                                      |
                       NumericOS API (FastAPI, SSE)
                                      |
                      Persistent Domain + Event Ledger
                       |        |         |          |
                  Knowledge  Experiments Agent sessions Skills Registry
                   Context    & evidence     |           |  canonical SKILL.md
                       |        |      AgentAdapter    |
                       |        |    Codex / Claude / Pi / OpenCode
                       |        |         |
                         Research Controller
                                |
                       Durable Job Supervisor
                                |
                     Local / Docker / SLURM
                                |
                        Telemetry + Validators
```

- DB + append-only event ledger: source of truth for operations and decisions; publish stream events *after* durable transaction.
- Git: authoritative for source modifications. Baseline immutable; use worktree per **independent coding task**, not per parameter-only execution; record exact executed SHA and diff digest.
- Artifact/metric store: checksum-addressed scientific inputs, outputs, plots and high-frequency telemetry; never put huge datasets into Git.
- Persistent worker/supervisor owns job lifecycle beyond CLI/browser processes; restarts reconcile unknown/in-flight states honestly.
- **Skills:** canonical repository-defined instructions, optional scripts and references; NOT a substitute for deterministic acceptance gates.
- **Provider independence:** all agent sessions invoke an `AgentAdapter` with a capability matrix and normalized event envelope. First production vertical slice: Codex App Server, fallback only by documented ADR if blocked. Claude Agent SDK and Pi RPC are planned real second adapters. OpenCode later as demand warrants. No tight coupling of domain records to provider ID.
- Provider authentication, permissions and any commercial embedded usage must be evaluated per vendor; don't assume end-user subscription authentication can be redistributed in a third-party product.

## 2. Canonical technology decisions

| Component | Initial choice | Why / later alternatives |
| --- | --- | --- |
| GUI | React + TypeScript + Vite; Tailwind/shadcn/ui | local browser now; optional Tauri later |
| Board | dnd-kit | typed cards, persisted sorting |
| Markdown+selection | read-only Markdown renderer, robust DOM selection+anchor service | BlockNote only for editable long-form documents |
| Graph | React Flow, only when evidence/decision graph earns it | editable workflow graph deferred to M5 |
| Backend | Python 3.12+, FastAPI, Pydantic | typed domain contracts and scientific integration |
| Persistence | SQLite WAL + migrations | PostgreSQL only if multiuser needs demand |
| Events | append-only DB event ledger + replayable SSE | websocket only for true bidirectional need |
| Coding agent (first) | Codex App Server adapter | structured events and sessions; Claude Agent SDK / Pi RPC next |
| Agent skills | Open Agent Skills `SKILL.md` in canonical `skills/` | per-provider discovery or project-local adapter installation |
| Job execution | `subprocess`/process groups/`psutil` | Docker and SLURM extensions later |
| Tracking | NumericOS experiment model and structured metrics | optional MLflow integration; do not reinvent MLflow internals |
| Provenance | Git, hashes, environment/command metadata | artifact store extended later |
| Security | local loopback default; explicit sandbox, approvals | remote auth later, no secret logging |

Official implementation research references (verify specific releases before coding):
- Agent Skills: https://agentskills.io/specification
- Codex App Server: https://developers.openai.com/codex/app-server
- Claude Agent SDK: https://platform.claude.com/docs/en/agent-sdk/overview
- Pi: https://github.com/badlogic/pi-mono
- React Flow: https://reactflow.dev/
- dnd-kit: https://dndkit.com/

## 3. One repository, one source of scientific skills

```text
numericos/
  AGENTS.md
  CURRENT_MILESTONE.md
  apps/
    web/                       # Research Board, conversations, explorer, observability
    api/                       # versioned REST+SSE; never second business logic
  packages/
    core/                      # Pydantic types/domain semantics
    persistence/               # migrations and repositories
    events/                    # event ledger+SSE
    cli/                       # `numericos` executable/client
    agents/                    # adapter contract, Codex; future Claude/Pi/OpenCode
    skills/                    # SkillRegistry, loader/installer, selector in M4
    context/                   # approved knowledge + context compiler
    experiments/               # project/hypothesis/protocol/experiment/run
    executor/                  # process lifecycle and scheduler adapters
    observability/             # telemetry, domain metric adapters
    validators/                # deterministic numerical validation gates
  skills/                      # SINGLE CANONICAL SOURCE for every agent
    scientific-method/SKILL.md
    research-code-style/SKILL.md
    numerical-validation/SKILL.md
    numerical-debugging/SKILL.md        # added M4
    numerical-benchmarking/SKILL.md     # added M4
    experiment-provenance/SKILL.md      # added M3
    runtime-observability/SKILL.md      # added M3
    research-loop/SKILL.md              # added M4
    pde-diffusion/SKILL.md              # M4 domain example
    sparse-linear-algebra/SKILL.md      # M4 domain example
    stochastic-abm/SKILL.md            # M4 domain example
  examples/
    heat2d-python/
    sparse-solver-cpp/
  tests/
    contracts/
    integration/
    e2e/
  docs/
    architecture.md
    SKILL_ARCHITECTURE.md
    AGENT_ADAPTER_CONTRACT.md
    adr/
```

Treat directories as conceptual modular boundaries within one local deployment, not as an invitation for premature microservices. Add package directories when code needs them, not as empty architecture theater.

### M1 Scientific Skill Registry minimum contract

- Discover `skills/*/SKILL.md` using frontmatter name and description; validate IDs, unique names, required paths, and size limits.
- Activate explicit skill IDs at project/session level. Provide a GUI checklist and a machine-readable list/install/activate service.
- Adapter prepares **per-agent project-local** skill discovery (copy/link/configure depending on provider/version and worktree). Do not modify global user skill directories without explicit approval.
- Verify actual provider discovery in opt-in integration test; store canonical file SHA-256/revision, selection and installation status on each agent session; never fake success from directory creation alone.
- The three initial skills are **instructional**: `scientific-method`, `research-code-style`, `numerical-validation`. They can recommend checks but cannot produce a passed validator result before M3.
- Additional domain overlays and intelligent skill selection belong to M4, NOT the initial registry; named required skills may be enforced by task profile.
- Skills may contain executable scripts and references: do not run untrusted scripts merely because the registry discovered a `SKILL.md`.

See `docs/SKILL_ARCHITECTURE.md` for the full design and test matrix.

## 4. Core domain entities and semantics

| Entity | Fields that matter | Ownership |
| --- | --- | --- |
| Project | ID, goal, root/worktree references | workspace |
| BoardCard | type, linked entity, **workflow_status**, sort order | workspace |
| AgentSession | provider/model/native ID, capability snapshot, selected skill manifest | adapter |
| Message/Revision | immutable original Markdown, version/digest | conversation |
| Annotation/Thread | exact versioned text anchor, Ask/Change/Note, local messages | conversation |
| KnowledgeItem | explicitly reviewed decision/constraint, scope, supersedes/provenance | context engine |
| ContextSnapshot | approved knowledge refs, skill manifest/digest, protocol refs and context hash | context engine |
| Hypothesis | claim, controlled factors, prediction, falsification | research controller |
| Experiment | protocol version, independent variables, metrics, acceptance gates | research runtime |
| Run | executed SHA, command, inputs/seed, env/hardware, agent+skill manifest | job supervisor |
| Metric/Event | source, timestamp, step, value/unit and causal IDs | observability |
| Validation/Evidence | validation implementation version, uncertainty, artifacts, verdict | validator |
| Artifact | checksum, URI, kind, linkage | artifact store |

Operational board status is **not** epistemic status. `Ask` about a claim is **not** approval; accepting a textual revision is **not** a source code change; a proposed hypothesis is **not** scientific evidence. Never silently promote.

## 5. GUI requirements — equal to backend priority

**Scientific Kanban:** cards for task, hypothesis, experiment, issue, decision; drag/drop and per-type details. State of work independently represented from evidence status.

**Main answer + side comments:** preserve natural full Markdown answer. Select an arbitrary span with mouse/keyboard and show **Ask / Suggest Change / Add Note**; open a small side thread leaving the source visible. An `Ask` stays out of main agent chat; `Suggest Change` creates a reviewable range diff and new immutable revision; `Note` requires no model. Repeated phrases, Unicode, overlapping anchors, Markdown formatting and revisions must be handled or explicitly marked unsupported. The original answer remains accessible.

**Context Inspector:** show approved constraints, open questions, inclusion reasons, obsolete decisions, skill IDs and versions, and exact frozen context snapshot sent to a new agent session.

**Experiment Explorer & Timeline:** compare baseline/candidates, hypotheses, runs, Git SHAs, signals, verdicts and justifications; a replay reads *recorded* events, never invents hidden internal model reasoning.

**Research control:** budget, experiment loop limits, resource/parallelism settings, pause/resume/cancel, approval gates, selected provider/skills, real job state, explicit unobservable metrics.

**Workflow graph (later):** executable multiagent graph separate from historical evidence graph. GUI not merely a decorative shell over a terminal.

## 6. Numeric observability contract

Levels: **L0** process/resource/stdout; **L1** parsed scientific logs; **L2** instrumented numerical metrics/checkpoints; **L3** domain-specific validators. Missing coverage is displayed rather than inferred.

- Agent traces (structured tool calls, decisions explicitly submitted, approvals) and numerical traces (solver iterations, residuals, invariants, performance, anomalies) have distinct producers but share project/research/experiment/run correlations.
- `NaN/Inf`, hard resource cap, process crash etc. can trigger deterministic guardrails. Suspected numerical divergence needs explicit domain threshold + window patience; noisy fluctuations alone are not proof.
- Summarize material events into concise model dossiers; high frequency samples remain in artifact/metrics storage, not LLM context.
- The supervisor, **not** an LLM or client process, owns job lifecycle, retries, timeouts and cancellation.
- Every scientific execution records the exact skill manifest active when the agent proposed its change, alongside source and input provenance.

## 7. External agent invocation and API shape

Expose stable versioned operations to GUI, CLI and APIs using **one backend**:

```text
numericos serve
numericos project list --json
numericos skills list --json
numericos skills validate --json
numericos skills install --agent codex --project PATH --json
numericos research submit research.yaml --agent codex --skills scientific-method,numerical-validation --json
numericos research status RESEARCH_ID --json
numericos research events RESEARCH_ID --follow
numericos research results RESEARCH_ID --json
numericos research pause RESEARCH_ID
numericos research resume RESEARCH_ID
numericos research cancel RESEARCH_ID
```

**These are desired future CLI commands, not existing implementations.** M0 provides only project/API CLI basics; M1 adds skill commands; M3–M5 add research commands as phases mature. Submissions return promptly with ID and idempotency handling. Parent callers can exit while a durable worker continues. Skill selection may be explicit, auto (M4+) or restricted by upstream agent. MCP/A2A optional adapters after stable native CLI/HTTP contracts.

## 8. Milestones — precise boundaries, ticket ownership, exit gates

### M0 — Foundation and first graphical project board

**Implement:** Python/React monorepo, FastAPI/SQLite, Project/BoardCard/Event, data migrations, CRUD, transactional event ledger, SSE event replay, minimal `numericos` CLI and real frontend persistence. Document adapter and registry contracts but no provider process yet.

**Gate:** create/drag/update card through UI/API, reload/restart and see same persisted state; replay ordered event log. No hallucinated AI message or metric.

### M1 — Real agent + selection-anchored conversation + skill registry

**Implement:** adapter interface and one real provider (**Codex App Server default**; ADR-documented fallback Claude/Pi after capability smoke test), provider/model selection, normalized tool/turn events, session lifecycle, read-only Markdown chat and arbitrary exact-text Ask/Change/Note sidebar, threaded isolation and immutable revisions; fuller dnd-kit board. **Also implement canonical Scientific Skill Registry now**: valid SKILL.md discovery, install and activation, persisted per-session digests, selection GUI and three baseline scientific skills.

**Gate:** real agent reply streamed to GUI; second repeated occurrence of same phrase correctly anchored, edited version persists, side question never pollutes main agent session, user can enable/disable a skill and the real provider actually discovers it. M1 skill instructions do not claim numerical validity.

### M2 — Explicit approved knowledge and context compiler

**Implement:** scoped decisions/constraints with human approval and supersession, source provenance, safe semantic conflict review, versioned deterministic context snapshots, inclusion inspector, selected skills/version manifest in snapshots.

**Gate:** user corrects a selected claim, explicitly promotes approved 'do not densify sparse matrix' constraint; a fresh agent receives correct relevant constraint/skill set and sources. Unpromoted side notes do not become requirements.

### M3 — Real experimental execution and numerical observability

**Implement:** Hypothesis/Experiment/Run, baseline, experimental protocols, immutable code/data/env provenance, local durable process supervisor, job status/cancellation, metric collectors, event emission and replay, first real numerical validators, comparison GUI and Git links. Bind M1 skill metadata to run provenance; add observability/provenance skills without duplicating registry.

**Gate:** a real C++ or Python solver run streams process metrics and actual numerical residuals with known coverage level; baseline/candidate results are compared under controlled conditions and survive restart; invalid numerical result rejected despite process exit code 0; no automatic merge.

### M4 — Bounded autonomous computational research

**Implement:** state machine `PLAN → IMPLEMENT → EXECUTE → OBSERVE → EVALUATE → DECIDE`, hypothesis/controls/predictions/falsification, context snapshots, stop/repair/approval gates, compute/walltime/run/token budgets, domain overlays and selected scientific validators. Extend M1 skill registry with task-based (reviewable) `SkillSelector` and domain skills for PDE, sparse algebra, ABM and ML; do not fork skill text across providers.

**Gate:** autonomous bounded runs make at least two distinct hypotheses, respect budgets and correct baselines, surface uncertainties and stop safely. Compare A: general coding agent, B: same agent/model + skill suite, C: B + NumericOS runtime on same tasks/budget and independent graders.

### M5 — Agent-callable integration and multiagent/HPC

**Implement:** full native CLI/HTTP/Python SDK contract, idempotent asynchronous delegated research, event streaming and JSON results, parent/child ownership rules, optional specialist multiagent graph engine, richer agent adapters (**Claude SDK, Pi RPC**, OpenCode optional), skill parity across agent providers, optional SLURM, MCP and A2A adapter.

**Gate:** parent agent submits an objective via `numericos` CLI, exits, later queries structured provenance/results; second provider can load the same exact canonical scientific skill; an optional multiagent workflow does not take over the run supervisor or alter immutable protocols silently.

## 9. Validation and evidence to build the right product

Test human workflow separately from numerical quality:

**Human usability:** compare linear coding agent chat vs NumericOS on decision retrieval, correction of ambiguous phrase, ability to locate an earlier experiment and continue after new session. Record time, errors, dropped constraints and task completion; do not rely only on user enthusiasm.

**Scientific quality:** evaluate known reference tasks: explicit heat equation CFL/stability error, wrong PDE boundary condition that still exits 0, sparse solver runtime-vs-error tradeoff, stochastic ABM replicate/variance. Compare same provider+model:
- **A** plain coding agent.
- **B** coding agent + NumericOS skills and tools (without research controller).
- **C** B + NumericOS persistent supervisor/observability/research controller.
- Optionally **D** C + multiagent; isolate added cost from improvement.

Track validated success rate, invalid claims, anomaly precision/recall, repeatability, compute cost per valid conclusion and decision retrieval time. Repeat tasks/seeds, blinded or independent evaluation where possible, report uncertainty and ablations. Do not assert broad superiority from a small pilot.

## 10. Engineering rules and release output

- AGENTS.md is an engineering brief, not an already-running runtime. Do not falsely report output from unimplemented modules.
- Small testable vertical slices, actual persisted events and visible proof, no 'fake' live sessions/results.
- Fail-fast on invalid scientific invariants; avoid defensive blanket exception wrappers or unbounded retry. Preserve security boundaries on agent-generated code and secrets.
- No implicit source merge to `main`, no destructive filesystem operations without approval. Budget enforcement belongs to worker.
- Each milestone handoff: changed files, API/DB migrations, real tests run and outputs, unresolved limitations, screenshots/UI tests, next small ticket.
- If a provider's API/version does not support a needed operation, record a capability gap and use an ADR-backed fallback, rather than inventing support.
