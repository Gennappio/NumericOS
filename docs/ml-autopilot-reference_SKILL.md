---
name: ml-autopilot
description: Plan, run, monitor, debug, and compare reproducible ML experiments using isolated Git worktrees, MLflow tracking, runtime telemetry, and evidence-based promotion gates. Use when improving, tuning, repairing, benchmarking, or automating machine-learning pipelines, including SLURM workflows.
compatibility: Requires Git, Python, an executable project training/evaluation command, and preferably MLflow. Works with CLI coding agents; SLURM is optional.
---

# ML Autopilot

## Mission

Operate an evidence-driven experimentation loop for a machine-learning pipeline. The agent proposes and implements experiments; a deterministic supervisor executes jobs, collects observations, enforces budgets, and judges fixed acceptance gates. Never promote a change solely because an LLM considers the result promising.

This file is a **procedure**, not an installed runtime service. If the repository lacks an experiment controller or instrumentation, implement the smallest necessary adapter and test it before claiming automation is active.

## Operating principles

1. Preserve an immutable baseline and comparison protocol.
2. Use one **Git branch + separate worktree per independent agent task**; use many MLflow runs inside it. Spawn another worktree only for concurrently modified code or a genuinely separate implementation hypothesis.
3. Record the precise executed source revision: Git SHA, dirty-state or diff fingerprint, environment/container digest, dataset version, split identifiers, preprocessing config, seed, command and hardware. Prefer checkpoint commits before each candidate run. A branch name alone is insufficient.
4. Keep datasets and large weights outside Git. Do not commit credentials, personal data, raw clinical data or model artefacts. Refer to approved immutable dataset URIs/checksums.
5. Protect the sealed test set. Tune on training/validation only. Use the test split only at a predetermined finalization point; never send its results back to the search loop for tuning.
6. Assign resource limits: GPU/CPU, RAM/VRAM, wall-clock, storage, maximum candidate runs and maximum LLM repair attempts.
7. Require human approval for external spend, destructive actions, access-policy changes, deployment, or replacing the production model. Never silently push to main.
8. Do not automatically retry all failures. Distinguish deterministic code bugs, transient infrastructure failures, numerical problems and invalid scientific comparisons.

## Step 0 — Inspect and establish a contract

Read project README, dependency files, entry points, evaluation scripts, data lineage and existing MLflow configuration. Identify whether jobs run locally, in containers, or under SLURM.

Create `experiments/experiment_contract.yaml` (or adapt the project's existing experiment schema) with:

- `objective`: task and scientific/operational question
- `primary_metric`, `direction`, `minimum_effect`, `aggregation`
- `guardrails`: max RAM, VRAM, latency, runtime, costs, and domain-specific constraints
- `baseline_ref`: immutable source SHA and baseline run ID
- `dataset_id`, `dataset_checksum`, `split_version`, `preprocessing_version`
- `seeds` and any group-aware or donor-aware splitting strategy
- `train_command`, `validation_command`, `smoke_command`
- `limits`: maximum attempts, parallel jobs, runtime and compute budget
- `promotion_policy`: score threshold, repeated-seed acceptance, required tests and reviewer

Do not invent datasets, metrics or acceptable thresholds. If unspecified, propose conservative defaults and mark them as assumptions. For cell datasets, explicitly check donor/sample leakage and batch confounding.

## Step 1 — Establish baseline

Run smoke tests, then the baseline using the contract's dataset and seed protocol. Log all results in MLflow, along with code SHA, command, environment, input dataset identifier and hardware. Capture stdout, stderr, status, wall time and peak RSS/VRAM independently from model metrics. Store a baseline summary. Do not optimize until baseline is reproducible.

Use MLflow for run history; use SQLite or a small durable event ledger for orchestrator state and job transitions. Neither MLflow nor Git alone is the authoritative runtime process supervisor.

## Step 2 — Create isolated agent task

From a clean base revision:

```bash
git worktree add -b agent/<task-id> ../worktrees/<task-id> <base-ref>
```

Use sanitized unique task IDs. Confirm target directory and branch do not exist before running the command. Execute the agent within the new worktree. Never alter the user's currently checked-out branch implicitly. A local experiment runner may execute several parameter-only runs from the same checkpoint commit.

Define a hypothesis for each candidate:

```yaml
hypothesis_id: h001
parent_run_id: baseline-run-id
change: "Replace dense normalization with sparse-safe normalization"
expected_effect: "Lower RAM without degrading macro-F1"
changed_surface: ["src/preprocessing.py"]
confounders_to_control: ["dataset", "split", "seed", "hardware"]
```

## Step 3 — Run with supervisor

The supervisor, not the LLM, must own process lifecycle, queueing, cancellation, signals, exit codes, timeouts and retries. Where available, expose an adapter interface:

- `launch(run_spec) -> job_id`
- `status(job_id) -> queued|running|succeeded|failed|cancelled|timed_out`
- `metrics(job_id) -> timestamped metrics`
- `logs(job_id, cursor) -> incremental log events`
- `resources(job_id) -> CPU/RAM/GPU/VRAM/time`
- `cancel(job_id)`

For local use, implement these with `subprocess`, `psutil` and a process-group-aware timeout. For SLURM, map them onto `sbatch`, `squeue`, `sacct`, `scancel` and scheduler output files. Detect unavailable scheduler accounting rather than reporting fabricated metrics.

Observe at reasonable intervals without dumping every log line into the model. Emit structured events only for material changes:

- `JOB_STARTED`, `HEARTBEAT`, `METRIC_UPDATED`, `RESOURCE_WARNING`
- `NAN_OR_INF`, `DIVERGENCE`, `CUDA_OOM`, `PROCESS_CRASH`
- `EARLY_STOP`, `JOB_COMPLETE`, `REGRESSION`, `IMPROVEMENT_CANDIDATE`

Use deterministic rules for NaNs, process crashes and hard limits. Detect statistical drift with an explicit window/patience and validation criterion; do not assume that a single noisy loss increase means divergence.

Every emitted event must carry `event_id`, UTC timestamp, `session_id`, `job_id`, `run_id`, executed `git_sha`, dataset reference, event type, severity, short evidence and links to full logs/artifacts. Retain a durable audit log. Redact secrets and personal data before sending any diagnostics to an LLM.

## Step 4 — Debug intelligently

When a run fails:

1. Freeze evidence: source SHA/diff, parameters, seed, environment, stack trace, recent telemetry and last successful checkpoint.
2. Classify: code error / resource limit / numeric instability / data problem / infrastructure / unknown.
3. If transient infrastructure failure, retry with backoff within a bounded budget; do not mutate model code.
4. If deterministic code failure, present the agent a *short event dossier* and relevant `git diff`, not the entire log history.
5. Ask the agent for a specific causal hypothesis and a minimal patch. Run static checks and a fast reproduction test before another full training job.
6. Permit at most the contract's allowed auto-repair attempts. On repeated failure, stop and request human review.
7. Use `git bisect` only when there is a deterministic executable good/bad test, compatible revisions and an established known-good commit. Otherwise compare candidate to baseline and avoid attributing causality from timing alone.

Never modify data splits, evaluation metrics or thresholds in response to a failing candidate without explicitly recording a protocol revision and creating a new comparison cohort.

## Step 5 — Evaluate and compare

Compare candidates against baseline on the **same dataset, splits, seed set, preprocessing and evaluation implementation**, unless the hypothesis explicitly requires a change. Track per-seed scores, aggregate effect, variance, guardrails, throughput, and peak memory. For costly training, use smoke and proxy runs first, but require full evaluation before promotion.

Possible verdicts:

- `REJECT`: invalid, failed guardrails or clearly worse.
- `INCONCLUSIVE`: insufficient statistical evidence or incomparable setup.
- `INVESTIGATE`: promising but requires replication, ablation or more data.
- `ACCEPT_CANDIDATE`: passes the predefined validation criteria.

`ACCEPT_CANDIDATE` does **not** mean production deployment. An approved finalization stage may run the sealed test set once under the agreed policy, followed by human review before merge or deployment.

Log one structured decision record per hypothesis:

```json
{
  "session_id": "task-001",
  "hypothesis_id": "h001",
  "source_sha": "<full-git-sha>",
  "baseline_run": "<mlflow-id>",
  "candidate_runs": ["<mlflow-id>"],
  "decision": "INVESTIGATE",
  "reason": "Macro-F1 improved on one seed; replication required",
  "next_action": "repeat on prespecified seeds"
}
```

## Step 6 — Commit, integrate and clean up

Use atomic descriptive commits after reviewable changes. Maintain links between commits and experiment IDs using MLflow tags or an experiment ledger. Never include large datasets or checkpoints in Git. If no candidate passes, preserve the experiment report but do not merge experimental code.

Before merge, check that no jobs still depend on the worktree, that the working tree is clean, and that required artifacts and audit records are persisted. Merge only after the agreed approval gate. Remove worktrees using `git worktree remove` and remove only branches known to be safely merged or explicitly marked for deletion; preserve useful failed-candidate history in the tracking ledger.

## Required user-facing report

Summarize:

1. Original goal and comparison protocol.
2. Baseline and all material candidate hypotheses.
3. Reproducibility provenance (Git SHA, dataset/split, environment, seeds).
4. Primary metrics with uncertainty and resource guardrails.
5. Crashes, fixes, retries and unresolved anomalies.
6. Verdict and evidence for each accepted/rejected candidate.
7. What was changed in Git, what was not merged and what needs approval.

Never claim statistical significance or autonomous recovery without actual recorded evidence. Never claim persistent background monitoring if no process or scheduler is running.

## Minimal implementation order

1. **MVP A**: existing training command + Git worktree + MLflow + baseline/candidate comparison.
2. **MVP B**: supervisor with structured events, timeout/cancellation, crash dossier and bounded repairs.
3. **MVP C**: SLURM adapter, parallel isolated candidates, resource budgets and automated comparison.
4. **Later**: dashboard, experiment prioritization and additional specialized agents only when measured value justifies them.

## Example request

"Optimize my scRNA-seq classifier for macro-F1, keeping peak memory below 16 GB. Preserve donor-disjoint splits and the sealed test set. Establish a baseline, create an isolated worktree, run at most 6 experiments with 3 seeds each, monitor jobs, debug deterministic failures up to 2 attempts per hypothesis, and submit a comparison report. Do not merge without my approval."
