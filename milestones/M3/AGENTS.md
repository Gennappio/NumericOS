# M3 / AGENTS.md — Experiment Engine, Git provenance and numerical observability

**Read root AGENTS, M0–M2 contracts and `docs/ml-autopilot-reference_SKILL.md`.** Implement M3 only. This is where NumericOS becomes a computational research runtime rather than just an excellent research conversation workspace.

## 0. Product outcome

Researcher selects a hypothesis card, defines measurable experiment, captures baseline, asks an agent to implement a candidate (or uses existing code), launches a real numerical executable, sees **live CPU/RAM/logs AND scientific metrics**, can inspect problems while it runs, compares candidate against baseline, and later reconstructs exactly what ran and why. An external CLI client and GUI observe the **same durable run**.

Domains: PDE solvers, C++ numerics, numerical optimization, sparse algebra, ABM/stochastic simulations, ML. **Do not hardcode ML concepts into generic run model** (training/validation splits only in ML adapters).

## Reuse M1 skill registry; add executable validity (do NOT reimplement skills)

- The M1 canonical Agent Skills procedures remain the sole source. M3 binds `numerical-validation`, `experiment-provenance` and `runtime-observability` to **real** run specifications, telemetry adapters and validator interfaces; add new canonical skills only when needed, with versioned metadata.
- Distinguish a loaded instructional skill from a **run-time gate**. Numerical stability, analytic-reference error, invariants, performance/reproducibility are evaluated by deterministic code or specified statistical protocols; the LLM can propose a test but cannot declare it passed.
- Every run saves agent provider/model (if known), activated skill manifest/digests, executed Git SHA, inputs, environmental metadata, validator versions and metric provenance. The GUI separates 'skill enabled' from 'validation passed'.
- Support numerical fields/metric extraction via explicit adapters or lightweight instrumentation, never pretend internal state can be inferred from CPU load alone.


## 1. Data model: different scientific layers

- `ResearchCampaign` (optional minimal parent) links objective and project; for initial milestone a Project+Hypothesis relation may suffice.
- `Hypothesis`: question/claim, causal rationale, prediction, falsification conditions, assumptions, epistemic status, source knowledge refs.
- `Experiment`: tests hypothesis through protocol with independent variables, controlled variables, fixed measurement procedure, metrics definitions and units, validation rule version, expected observations, comparison cohort.
- `Run`: concrete code revision+arguments+inputs+seed+environment+hardware+executor/job ID+actual wall time and status. Many runs share experiment/code, e.g. different timestep/mesh size/seed.
- `MetricSeries`: time/step-indexed numerical values with units and provenance; store high-rate samples in bounded/chunked files rather than flooding SQLite.
- `ValidationResult`: named check, algorithm version, outcome `PASS/FAIL/INCONCLUSIVE/NOT_EVALUATED`, threshold/uncertainty, evidence pointers, grader identity.
- `Artifact`: image/plot/checkpoint/output mesh/report URI, checksum, size, format, experiment/run owner.
- `EvidenceRecord`/`Decision`: comparison across run cohort and baseline, supported/contradicted/inconclusive/investigate; not equivalent to workflow complete.

Never assume one `git commit == experiment == run`. A single code version can have many runs; a hypothesis can require several experiments; multiple candidates can be tested across comparable cohorts.

## 2. Experiment contract (minimum required)

```yaml
id: exp-heat2d-01
hypothesis_id: h-stability-01
question: "Does reducing dt restore stability for the explicit scheme?"
prediction: "Unstable residual growth disappears below stability threshold"
falsification: ["Persistent divergence under all controlled smaller dt"]
independent_variables:
  dt: [0.02, 0.01, 0.005]
controls:
  mesh_id: grid-128
  initial_conditions_checksum: sha256:...
  boundary_condition_version: bc-v1
  solver_revision: <immutable-sha>
metrics:
  - {name: residual, unit: dimensionless, sampled_by: instrumentation}
  - {name: l2_error, unit: dimensionless, sampled_by: output_postprocessor}
  - {name: wall_time, unit: s, sampled_by: supervisor}
validation_policy:
  reference: analytic-or-baseline
  convergence_criterion: predefined
limits: {wall_seconds: 300, cpu_cores: 4, max_ram_gb: 8}
```

These are sample values and an example schema, not established scientific thresholds. For heat equations the condition depends on dimensionality, discretization and coefficients. **Never bake one universal threshold for all solvers.** Freeze the comparison protocol before looking at candidate results or record a new cohort when it changes.

## 3. Git and reproducibility policy (adapt ML Autopilot faithfully)

- Protect baseline ref and comparison/evaluator implementation. Record executed **full SHA**, cleanliness/dirty diff digest, dependency versions or image digest, input checksums, command and arguments, hardware, numerical precision/compiler flags and seed (when applicable).
- Use **one branch + worktree per independent agent code-editing task**. Do not create a branch per parameter-only run. Multiple run configurations of identical code use same SHA/worktree; independent competing code hypotheses can have distinct worktrees.
- Never implicitly modify user's checked-out branch; check target path/branch collisions, handle stale worktrees conservatively, no silent `git clean`, checkout resets, force pushes or merges.
- Prefer committed checkpoint before numerical candidate run; if dirty tree allowed under explicit policy, capture exact diff fingerprint and ensure it can be reproduced. A SHA of an uncommitted worktree alone is not sufficient.
- Keep large data, weights, solver dumps and numerical mesh artefacts out of Git; use immutable checksums/URIs.
- Record optimization build flags and environment; distinguish performance reproducibility from bitwise numerical reproducibility, particularly stochastic or parallel numerical runs.

## 4. Supervisor as an independent process

Build a **real long-lived local daemon/worker** (can be a single Python process, but NOT a FastAPI background coroutine tied to request lifetime or a child orphaned accidentally when CLI exits).

Minimum interface:

```python
launch(run_spec) -> job_id
status(job_id) -> queued | running | succeeded | failed | cancelled | timed_out
metrics(job_id, cursor) -> metric events
logs(job_id, cursor) -> incremental log events
resources(job_id) -> measured cpu/rss/optional gpu info
cancel(job_id) -> cancellation acknowledgement
```

Tasks:
- start subprocess with argv arrays, no vulnerable shell interpolation; bounded working directory/env and resource limits; capture stdout/stderr incrementally, truncate/rotate with artifact links for full logs.
- accurately persist job start/end, exit status, OS PID+start-time identity, project/run linkage, heartbeats, deadlines, cancellation intent and actual termination. Group-aware cancellation to avoid leaked solver child processes.
- on API restart, worker and jobs continue, GUI reconnects to ledger. On daemon restart, attempt safe reconciliation with OS process identity; if uncertain mark `UNKNOWN/LOST` rather than claiming job succeeded. Do not promise resilience to host power loss unless demonstrated.
- distinguish transient infrastructure faults, deterministic code failures, numerical instability and invalid scientific comparisons. Automatic retry only transient faults under an explicit budget; never hide retry history.
- event ledger is authoritative process history, filesystem/artifact storage holds bulky details. SSE streams an incremental view.

## 5. Observability with four coverage levels

`L0` automatic process: exit code, wall time, CPU, RSS, I/O where supported, stdout/stderr, basic resource/timeouts. **No numerical truth inferred.**

`L1` parser adapter: extract known signals from solver logs or output files (residuals, losses, discretization errors, mass conservation, objective progression). Parser schema/version and units recorded; malformed samples diagnosed.

`L2` explicit instrumentation: light optional hooks or JSONL events from Python/C++ program; recommended API design `metric(name, value, step, unit?)`, `checkpoint`, `event` (implementation can be JSONL to stdout/file). Agent should instrument only real scientific observables required by the contract, not rewrite whole solver into telemetry framework.

`L3` domain validator: PDE mesh convergence, invariants, stability conditions, reference solutions, sparse algebra residual, optimization constraint satisfaction, stochastic confidence intervals, ML leakage controls as specialized plugins.

GUI shows **coverage** and unknowns per run (`CPU/RAM ✓`, `numerical metrics unavailable`, `validator not configured`). No generic claim of 'fully observable'. A NaN is a hard event; a transient noisy change in an optimization metric is not automatically divergence.

Example JSONL emitted by numeric instrument (spec):

```json
{"schema":"numericos.metric.v1","run_id":"run-001","name":"residual_l2","step":42,"value":0.00032,"unit":"dimensionless","timestamp_utc":"2026-10-09T13:14:15Z"}
```

Validate finite/non-finite handling explicitly (`NaN`/`Inf` serialized as typed events, not non-standard JSON number literals). Measurement is time-stamped at source if trusted, or at collector, and tagged. Do not overwhelm database or LLM with every sample; windowed aggregations/alerts and raw chunked artefacts.

## 6. Numerical validation and honest science

- Establish a baseline run that meets declared reproducibility criteria before optimization.
- Compare same conditions (input/mesh, boundary conditions, precision, hardware as applicable, seeds, evaluator) unless the hypothesis explicitly changes one. Never compare incompatible outputs without labeling `INCOMPARABLE`.
- Apply explicit validators: checks on finite values, errors against reference, physical conservation, convergence order when expected, stable trends with meaningful patience/window. Distinguish a code crash vs convergence failure vs successful exit but scientifically invalid output.
- For stochastic studies require replicate seeds and meaningful uncertainty; do not treat one lucky run as discovery.
- Keep evaluation policy version fixed; if changed, create a new comparison cohort and mark old data non-comparable by default.
- Verdict classes: `REJECT`, `INCONCLUSIVE`, `INVESTIGATE`, `ACCEPT_CANDIDATE`, `NOT_EVALUATED`. Candidate acceptance is **not** permission to merge/deploy.

## 7. GUI / UX requirements

Experiment Explorer integrates with M0/M1 board and M2 knowledge:
- Hypothesis card opens hypothesis+controls+predictions+falsification and linked experiments.
- Experiment view includes immutable protocol, run table, candidate vs baseline plots with units, validators and exact source/input refs.
- Run Monitor shows actual status, process resources (real observed points), stdout/stderr, numeric series, warnings, event timeline, coverage level, artifact previews; automatically marks uninstrumented metrics.
- Decision timeline links **hypothesis → code diff/commit → executable run → observation/metric → evaluation → next proposed action**; clicking any event opens evidence, not fabricated explanation.
- Console-like deep technical logs are expandable, not the default visual experience (avoid the same chat wall problem).
- Can resume observing a long-running job after GUI/API reconnect and distinguish paused/cancelled/unknown states.

## 8. Suggested endpoints and CLI

```http
POST /v1/hypotheses
POST /v1/experiments
GET  /v1/experiments/{id}
POST /v1/experiments/{id}/runs
GET  /v1/runs/{id}
GET  /v1/runs/{id}/metrics?after=...
GET  /v1/runs/{id}/logs?after=...
POST /v1/runs/{id}:cancel
GET  /v1/runs/{id}/artifacts
GET  /v1/experiments/{id}/comparison
```

CLI examples: `numericos experiment run exp.yaml --json`, `numericos run status ID --json`, `numericos run watch ID`, `numericos run cancel ID`. All must talk to persistent supervisor through same backend; include correct exit codes.

## 9. Work tickets

1. **M3-T01 — Domain model + migrations:** Hypothesis/Experiment/Run/validation/artifact; explicit links to board/knowledge/event IDs; schema/transaction tests.
2. **M3-T02 — Provenance:** Git SHA/dirty diff, worktree policy and immutable input/environment refs, prevent mutating user repo, test multi-run same commit.
3. **M3-T03 — Persistent local supervisor:** launch/cancel/reconcile, subprocess limits, event ledger, API restart, process group, failed-job classification.
4. **M3-T04 — Numeric adapters:** heat2d Python & sparse/C++ sample, stdout/JSONL parser, time series, anomaly events, coverage, sample output tests.
5. **M3-T05 — Validators and comparison:** fixed baseline/candidate cohorts, numerical checks and warnings, replayable verdict records.
6. **M3-T06 — Experiment Explorer/Run Monitor:** real charts, run detail and timeline linking code/results, UI e2e + independent baseline validation.

## 10. Rigorous acceptance experiments

**Heat equation 2D**: provide a small well-characterized explicit scheme with known stable/unstable timestep settings for its exact discretization; actual run emits residual/error series. Supervisor detects non-finite or configured instability with window criterion, halts if guardrail requires, labels evidence and supports basic diagnosis without inventing cause.

**Wrong boundary condition**: program exits zero; validator catches mismatch to known solution or boundary invariant. Shows difference between software success and scientific failure.

**Sparse kernel candidate**: benchmark fixed matrix/input/precision, same hardware, record timing and numerical residual. Candidate faster but violates error criterion => REJECT. Candidate meets criteria => ACCEPT_CANDIDATE, no merge.

**Stochastic small demo**: multiple seeded runs, variance displayed, one favorable seed not promoted as reliable improvement.

**Persistence**: API/browser restart while supervisor runs does not kill process; later reconnect shows exact real run state and trace. Kill worker and test safe reconciliation or UNKNOWN state; no fake completed job.

**Provenance**: fresh developer can reproduce at least one run (within declared platform/tolerance) using exported contract, Git ref and input checksum.

## 11. Security / exclusions

Agent-authored code is a real execution risk. For local trusted MVP require explicit trust of project and restrict to approved workspace/resource envelope; before remote/multiuser usage enforce a sandbox/isolation policy. No destructive actions without permission. No silent data upload to LLM/third-party telemetry. No automatic universal scientific validation, no SLURM, no complex multiagent research loop (M4/M5). MLflow/OTel integration optional if it adds clear benefit; do not make it a new source of truth for running process state.

**Exit gate:** an actual Python or C++ numerical program runs under a persistent supervisor; real numeric and system telemetry, scientific validators, Git/input provenance and baseline comparison appear coherently in GUI and API. A failed/unstable experiment remains inspectable as evidence.
