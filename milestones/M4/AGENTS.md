# M4 / AGENTS.md — Scientific skills and bounded autonomous computational research

Read root `AGENTS.md`, M2 Context and M3 Experiment/Execution contracts; adapt `docs/ml-autopilot-reference_SKILL.md` beyond ML. **Implement M4 only**. This is the first milestone that closes an autonomous scientific feedback loop. It must not devolve into 'run agent until it says something interesting'.

## 0. Scientific behavior to deliver

Researcher or parent agent provides an objective and budget for a numerical project, e.g. 'reduce sparse solver wall time while keeping relative error below a known threshold'. NumericOS establishes baseline, formulates **explicit hypotheses**, plans discriminating experiments, implements candidates through the selected AgentAdapter, runs with the durable supervisor, observes numerical/resource evidence, applies independent validators, compares runs and decides whether to reject, investigate, replicate or test another candidate. It stops when budget/goals/limits are reached, preserving all evidence and leaving candidate code unmerged until human approval.

**No claim that an LLM discovers scientific truth.** Deterministic controller enforces policy; LLM proposes hypotheses, plans and interprets, never self-certifies scientific validity or reports unobserved runtime metrics as facts.

## 1. Research loop and separation of responsibilities

```text
PLAN -> HYPOTHESIZE -> DESIGN -> IMPLEMENT -> EXECUTE
  ^                                        |          |
  |                                        |          v
  +---------- DECIDE <- EVALUATE <- OBSERVE <- MONITOR
```

Each transition is persisted as a state-machine event, with run/candidate/context IDs and policy version. M4 starts with **one supported agent** (Codex by default, or any integrated provider) that takes scientist/coder/reviewer roles through typed tasks if needed; do not multiply agents by default. Research controller is a **deterministic program**, not an endless LLM prompt.

- Controller: budget accounting, transitions, durable queued/active/completed jobs, retries, hard-stop and approval gates, event sourcing, idempotent transitions.
- Agent adapter: generate/test hypothesis, propose minimal diff, review code, interpret evidence in structured output and suggest next experiment. Its answer may be wrong; validators gate effects.
- Supervisor: owns processes/resources/telemetry, cancellation, timeouts and failure classification.
- Validator: independent numerical test policy + performance comparison, baseline integrity, uncertainty rules.
- Context Compiler: snapshots approved constraints/decisions and relevant experiment observations; agent does not get entire raw logs or full chat history.

## 2. Full experiment/hypothesis protocol

Before implementing any candidate, obtain/derive and persist:

1. Research question / objective (numerical or operational), reference implementation and applicability scope.
2. Mechanistic hypothesis: what change, why it might work, and conditions under which it should fail.
3. Controlled variables and deliberately varied parameters; numerical discretization/mesh/precision, initial/boundary conditions and seeds as applicable.
4. Predicted effects and measured quantities with units and accuracy/performance tradeoff.
5. **Falsification / rejection conditions specified before seeing outcome**; guardrails, comparator, tolerance and uncertainty requirements.
6. Resource budget: runs, attempts, code revisions, max wall time, CPU/GPU limits, storage and monetary limit if applicable.
7. Scientific outcome class + evidence links, unresolved confounders, next step suggested vs executed.

Distinguish an **exploratory search** (candidates selected adaptively on validation data) from **confirmatory validation** (sealed evaluation protocol, no retuning against final holdout). In simulation, this may mean independent reference meshes/cases; in ML, sealed test data; in stochastic ABM, withheld seeds/configurations. Define per-domain confirmation policy and avoid leaking confirmatory results back into exploration.

## 3. Research budget / loop configuration

Example proposed contract:

```yaml
research:
  id: research-001
  objective: "Accelerate iterative sparse Poisson solver"
  project_id: project-001
  mode: bounded_autonomous
  baseline_experiment_id: exp-base
  limits:
    max_candidate_hypotheses: 10
    max_experiments: 20
    max_total_runs: 50
    max_parallel_runs: 3
    max_llm_repair_attempts_per_candidate: 2
    max_wall_clock_minutes: 180
    cpu_core_budget: 4
    max_ram_gb_per_run: 8
  stop:
    target_speedup: 1.5
    max_relative_error: 0.0001
    no_improvement_rounds: 4
  approval:
    merge_to_main: human_only
    protocol_changes: human_review
```

Proposed values are examples; **do not invent default scientifically acceptable errors or budgets**. Missing required policy must be surfaced as assumptions or blocked. Enforce budgets server-side even if agents ignore prompts. `max_parallel_runs` counts concrete numerical jobs, not agents. Distinguish numerical solver iteration count from agent turns and research experiment count. Runtime job duration and total elapsed research duration are separate knobs.

## 3a. Scientific skills are an M1 foundation, not a new M4 subsystem

M4 must **extend**, not reinvent, the NumericOS Scientific Skill Registry introduced in M1. Skills are activated per objective, session and research step; maintain `task → selected skills → rationale → canonical manifest digests → agent session → run → evidence` traceability.

- `SkillSelector` starts with deterministic domain/task tags and user selection, augmented optionally by LLM suggestions. It may recommend skill bundles but **cannot** silently activate untrusted skills, change numeric acceptance gates or override project-specific approved constraints.
- Provide `always-on` minimal scientific-method/research-code-style when appropriate, optional numeric/domain overlays, and per-agent/step selection. Show an exact preview of the skill set in the GUI before starting expensive autonomous loops.
- Runtime checks remain code. Skill `numerical-validation` describes what tests to run, while `ValidationGate` executes and records outcome. A skill-only instruction must not mark an experiment `VALIDATED`.
- Benchmark **A** vanilla same provider/model, **B** A + real activated scientific skills, **C** B + persistent runtime and scientific supervisor; control budget to isolate incremental value. Optional multiagent is deferred to M5.


## 4. Scientific skill library (procedures, not empty prompt labels)

Extend the M1 canonical SKILL.md files and add skill directories when needed. Follow the Agent Skills specification: frontmatter **name** and **description** are required; put when-to-use, prerequisites, inputs, invariants, protocol, expected evidence, failure modes and examples in the body or compatible metadata. The M3 runtime executes numeric tests; a skill text alone never certifies a run. Minimum cross-domain core:

- **`scientific-method`** — formulate testable hypotheses, predictions, controls, falsification rules, experimental meaning of outputs, inconclusive reporting, assumptions.
- **`research-code-style`** — minimal readable scientific code; clear equations/algorithm data flow; no over-defensive wrappers, silent exception swallowing, unnecessary feature flags or speculative microservices. Fail fast on genuine invalid dimensions/inputs/NaNs and preserve critical numerical assertions; benchmark without side effects.
- **`numerical-validation`** — conservation laws, invariants, discretization/mesh refinement, reference analytic solutions, residual norm vs actual solution error, roundoff/sensitivity, stochastic replication, method-specific convergence; do not apply arbitrary universal CFL/order thresholds.
- **`numerical-debugging`** — classify code bug, numerical instability, conditioning, data quality, resource and infrastructure failure; gather minimal crash/evidence dossier then propose smallest discriminating test and patch; no random parameter fiddling without hypothesis.
- **`experiment-provenance`** — immutable baseline, exact executed Git SHA/dirty-state, one worktree per independent code-edit task, several parameter runs per revision, environment/input checksums, evidence ledger and no premature merge.
- **`runtime-observability`** — L0–L3 telemetry, distinguish measurable vs unobservable quantities, numerical anomaly detection from explicit rules/windows, concise event dossier for agent and full details for user.
- **`numerical-benchmarking`** — warmups vs measurements, fixed hardware/load, comparator and reference, meaningful multiple runs, numerical correctness gates, uncertainty, performance regression handling.
- **`research-loop`** — budget semantics, agent turn specification, stop conditions, exploration vs confirmation, verdict rules and human review.

Domain overlays can initially be lightweight, but real examples/tests: `pde-diffusion` (mesh/timestep stability for concrete scheme), `sparse-linear-algebra` (solution error/residual and performance), `stochastic-abm` (seed replication and variance), `ml-pipeline` (data leakage/splits). CFD/FEM and richer ABM plugins later. Skills should be independently testable and invocable via agent instructions/tools; a copied prompt file without actual validation hooks is not sufficient proof of automation.

## 5. Decision policy and evidence evaluation

Use verifiable decision records:

```json
{
  "research_id": "research-001",
  "hypothesis_id": "h04",
  "baseline_run_ids": ["r00"],
  "candidate_run_ids": ["r18", "r19", "r20"],
  "validator_version": "numeric-v1",
  "verdict": "INVESTIGATE",
  "evidence_refs": ["metric-series-residual", "resource-summary"],
  "known_uncertainties": ["No large-mesh scaling measurement"],
  "proposed_next_action": "Run larger sparse test matrix",
  "status": "proposed"
}
```

`ACCEPT_CANDIDATE`: passed predeclared evaluation; not merge/deployment. `INVESTIGATE`: promising but uncertain. `INCONCLUSIVE`: underpowered/noncomparable/instrumentation insufficient. `REJECT`: invalid/regression/failed guardrails. `STOP`: budget/authorization. **An LLM rationale is not evidence by itself.** Any action that changes test protocol or baseline creates an explicit new version/cohort and may require human review.

For complex causes, include explicit competing explanations and choose a discriminatory next experiment, not always a micro-optimization. The system should be allowed to conclude 'not enough evidence'.

## 6. Runtime loop behavior

- Every step starts with a frozen context snapshot (M2), hypothesis/experiment contract and policy hash. The LLM receives a concise dossier: relevant code/diff, prior candidates, metric summaries, failing validator messages and open uncertainties; no mass log ingestion.
- Agent edits in isolated worktree; cheap smoke/reproduction check before costly full experiments. If baseline not reproducible, stop before optimization.
- Hard numerical invalidity (NaN/Inf, code crash) triggers correctly classified events and cancels run when contract mandates; monotonicity/divergence requires method-specific threshold and window patience.
- Retry only transient infrastructure faults using bounded backoff. On deterministic bug, ask minimal hypothesis-driven patch bounded by repair attempts. On repeated failure, preserve artifacts and stop candidate.
- Same code SHA may yield many parameter/seed runs. Every run is linked to hypothesis and evaluation cohort.
- Enforce no uncontrolled spend/destructive actions, no force git reset/merge, human approval for merge/push, execution beyond accepted trust boundary or revised acceptance threshold.
- Parent/child step IDs and lineage allow GUI to trace 'H → code → run → observation → decision'.

## 7. GUI behavior

- Research settings view with understandable controls: maximum number of experiments, loop iteration/attempt limits, wall time, parallel runs, costs, CPU/RAM, target/guardrail, auto-pause settings; show budget consumed and remaining.
- Research loop timeline and **decision graph**, with each node expandable to its hypothesis/patch/run/metric evidence. Don't confuse decision graph (historical) with workflow editor (future, M5).
- Scientific Kanban cards created/updated from real hypotheses/experiments and labeled proposed/running/review/finished operationally; scientific verdict separately shown.
- Agent activity view shows assigned role, actual current action, structured reason submitted at transition, tool calls and failure events. Expand technical details on demand — avoid giant chat-wall output.
- Pause/resume/cancel controls, pause point is safe (no mid-run destructive modification), approval-required banners, worker health and disconnected state.
- At completion, generate compact top-level report plus links to full evidence; preserve rejected and failed candidates as learning, not hidden history.

## 8. Work tickets

1. **M4-T01 — Controller state machine:** persisted transitions, idempotency/restart safety, contract validation, budget enforcer with tests.
2. **M4-T02 — Extend M1 scientific skill registry:** reuse its versioned canonical skills; add domain overlays (PDE, sparse algebra, stochastic ABM, ML), runnable numerical examples, specific validator binding and documented scientific limitations; do not fork provider-specific copies.
3. **M4-T03 — Hypothesis planner + skill selector:** structured typed outputs from `AgentAdapter` (Codex/Claude/Pi according to available adapters); deterministic + reviewable task-to-skill selection with explicit forced/forbidden skill overrides, reason/expected effect/falsification; worktree integration and code review.
4. **M4-T04 — Execution/evaluation/decision loop:** M3 job supervisor, validated metrics, comparison cohorts, evidence-based decision record, deterministic stop and pause gates.
5. **M4-T05 — Scientific loop GUI:** loop settings, budget status, event/decision graph, evidence links and approval actions.
6. **M4-T06 — Benchmark / ablation:** A) selected agent alone, B) **same agent/model** + scientific skills/tools, C) B + NumericOS loop. Same models/prompts/budgets where meaningful; independent graders. Report limitations.

## 9. Independent validation suite

Prepare known-test cases, not just tasks the LLM declares completed:

- **PDE stability:** explicit heat equation implementation with correctly defined stability limit and deliberately unstable variant. Validate diagnosis & action with a reference grader.
- **PDE boundary defect:** running executable exits zero but violates analytical/boundary criteria; NumericOS must not mark scientifically valid merely due to exit code.
- **Sparse optimization:** a fast but numerically wrong candidate should be rejected, slower accurate candidate compared fairly, correct faster candidate considered for replication.
- **Stochastic ABM:** candidate appears better for one seed but not across replicates; NumericOS should flag uncertainty and avoid premature scientific claim.
- **Budget pressure:** max runs/LLM attempts/wall time reached while jobs pending; controller stops submitting, correctly handles in-flight jobs according to policy and reports consumption.
- **Crash classification:** transient worker interruption vs deterministic Python/C++ crash vs numerical divergence; correct distinct repair policy.
- **Context integrity:** accepted 'no dense conversion' project constraint applied in all code candidates; proposed-but-unapproved notes do not become hard rules.
- **No merge:** best candidate passes validators, yet `main` remains unchanged until user approval.

Metrics: validated task success, invalid scientific claim rate, reproducibility, missed anomalies/false alarms, compute cost per correct result, user interventions, time to trace a decision. Repeated trials and uncertainty; **ablate observability and context modules**, not just count agent output tokens.

## 10. Exclusions

No universal discovery agent, automated publication/paper submission, research literature scraping, new LLM inference engine, forced multiagent graph, autonomous change to scientific acceptance criteria, full HPC scheduling or remote SaaS. No declaring significance where the experiment did not measure it.

## 11. Exit gate

Submit a research objective with measurable constraints → autonomously formulate at least two genuinely distinct candidate hypotheses → instrument/test one or more real numerical programs → observe/evaluate/choose next action with structured evidence → stop correctly on budget/target/invalidity → inspect complete graph and Git provenance in GUI → leave candidates unmerged and present concise report. Resume after safe controller restart without repeating already-completed jobs. Only advance to M5 if comparison with the same chosen agent + skills shows useful added value or the remaining gap is clearly measured.
