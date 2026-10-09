# M5 / AGENTS.md — External agents, programmable multiagent research, HPC and interoperable CLI/API

Read root `AGENTS.md`, M4 loop controller contracts and this file. Implement **M5 only** after M0–M4 gates. The user's long-term goal is a modular research ecosystem: **NumericOS is one building block** in larger scientific multiagent systems. It must be callable without requiring MCP; CLI and native APIs are first-class. At the same time, NumericOS itself may coordinate specialist agents when justified.

## 0. Ownership and design philosophy

There may be a parent Research Orchestrator that reads literature, formulates broad hypotheses, delegates computational studies to NumericOS and synthesizes results. NumericOS **owns the delegated computational campaign** (hypotheses/experiments/runs, supervisor, local scientific evidence and budget within authorized scope). Parent owns overall research objective. No two independent controllers mutate the same experiment simultaneously.

Provide three NumericOS roles/modes:

1. **Tool mode:** upstream agent designs hypothesis/protocol; NumericOS executes/observes/validates with no autonomous candidate generation.
2. **Bounded research mode:** upstream delegates objective+bounds, NumericOS plans experiments/implements code/decides within budget and approvals.
3. **Collaborative mode:** parent receives intermediate evidence, suggests protocol revisions/child hypotheses, and controls explicit approval gates while NumericOS owns jobs.

Multiagent should be **opt-in**. A single strong agent may be cheaper, faster and more consistent. A role (`scientist`, `coder`, `numerical_reviewer`) need not mean a permanently running independent LLM. Deterministic supervisor/validator remains outside agent identity.

## 1. Agent-callable API contract (highest priority)

All clients invoke the same domain services: browser GUI, `numericos` CLI, Python SDK, HTTP API, and optional MCP/A2A transports. First deliver stable CLI/HTTP; wrappers later.

Stable operations:

```text
submit_research(spec, idempotency_key) -> research_id + accepted state
get_research(research_id) -> status, budgets, outstanding approvals
list_experiments(research_id) -> structured IDs and evidence refs
observe(research_id, after_event_id) -> stream or page events
get_results(research_id) -> machine-readable verdicts, provenance, artifacts
pause(research_id) / resume(research_id) / cancel(research_id)
propose_protocol_revision(research_id, revision) -> reviewable change request
get_capabilities() -> supported executors, modes, metrics and protocol versions
```

Recommended CLI examples (proposed to implement):

```bash
numericos research submit experiment.yaml --json --idempotency-key user-task-001
numericos research status RESEARCH_ID --json
numericos research events RESEARCH_ID --follow --jsonl
numericos research results RESEARCH_ID --json
numericos research pause RESEARCH_ID --json
numericos research resume RESEARCH_ID --json
numericos research cancel RESEARCH_ID --json
numericos capabilities --json
```

**Contract rules:**
- `submit` returns promptly with `accepted/queued` + durable ID; it does **not** wait for experiments to finish. Caller can terminate safely.
- STDOUT strict JSON/JSONL in machine modes; diagnostic logs to STDERR; documented nonzero exit/error codes; schema version field and stable IDs.
- `idempotency_key` scoped to caller/project: replay identical submission returns same ID, conflicting payload with same key => explicit conflict, not duplicate campaign.
- Event stream resumable with cursor / `Last-Event-ID`. Every event has cross-system trace/correlation ID, producer, parent task ID where known and UTC time; events may arrive late; avoid claiming exactly-once delivery across networks. Ensure idempotent consumption.
- `pause` stops future transitions at safe boundary; policy for already-running jobs explicit. `cancel` requests cooperative stop and enforces supervisor termination if needed, returning progress until terminal state.
- Structured results distinguish `COMPLETED`, `CANCELLED`, `FAILED`, `INCONCLUSIVE`, `NEEDS_REVIEW`; return evidence URLs/URIs, Git revisions, scientific and operational status separately, known limitations and next-step recommendation.
- No clipboard/chat dump as a substitute for an API result. Parent need not inspect LLM transcripts to decide next step.

## 2. Request/response examples (design schemas)

Request:

```yaml
schema_version: numericos.research.v1
caller:
  parent_task_id: lab-quest-012
  correlation_id: trace-123
project:
  id: project-solver
  baseline_ref: main
objective: "Improve sparse Poisson solver performance at fixed relative error"
mode: bounded_research
budget:
  max_experiments: 20
  max_parallel_runs: 3
  max_wall_minutes: 240
validation:
  invariant_policy_ref: solver-validation-v2
  baseline_required: true
observability:
  require_system_metrics: true
  require_numerical_signals: ["residual_l2", "solution_error"]
permissions:
  code_change: true
  merge_to_main: false
```

Response:

```json
{
  "schema_version": "numericos.research-result.v1",
  "research_id": "res-001",
  "operational_status": "COMPLETED",
  "scientific_verdict": "INVESTIGATE",
  "evaluated_hypotheses": 7,
  "best_candidate": {
    "hypothesis_id": "h-04",
    "run_ids": ["run-022", "run-023"],
    "git_sha": "<full-git-sha>",
    "metrics": {"speedup": 1.4, "relative_error": 0.00008}
  },
  "evidence_refs": ["numericos://res-001/summary", "numericos://run-022/logs"],
  "uncertainties": ["scaling not tested on a larger matrix"],
  "recommended_next_action": "validate_on_larger_matrix",
  "merge_performed": false
}
```

These values/URIs are ILLUSTRATIVE, not measured results or functioning transport yet. Artifact URI resolution and authorization policy must be documented. No 'high confidence' by unvalidated model self-report.

## 3. Adapter mechanism — CLI/native before MCP

- **CLI and HTTP** are canonical remote/control surfaces. Python SDK can be a typed thin wrapper over HTTP/core but must not implement divergent business logic.
- **MCP** adapter maps research ops to tools/resources if agent ecosystem uses MCP. MCP registration/trust is managed separately, not a prerequisite for CLI or NumericOS internal execution.
- **A2A** adapter may expose NumericOS as delegated task service (status, streaming/artifacts) where appropriate; don't make adoption mandatory, verify supported task semantics at implementation time.
- **Codex/Claude/Pi/OpenCode** adapters implement one versioned `AgentAdapter` contract with real capability negotiation. M1 supplies one real provider (Codex by default); M5 brings a second full real provider and subsequent adapters when needed. Tool calling, approval, skill discovery and resume vary; preserve the truth of what each adapter supports. Unknown = unavailable, not simulated. Never make the first provider mandatory for all future workflows.
- **External orchestration** could come from a Python script, Prefect/LangGraph, agent's CLI tool, custom agent graph; don't force the user to install particular graph framework.
- Wrap capabilities like `launch_job`, `query_job`, `get_scientific_evidence`, `request_implementation`, `submit_hypothesis` as structured, testable interfaces. Descriptions are not executable truth.

## 3a. Cross-provider skill contracts and delegated selection

- The upstream agent or orchestrator may pass `skill_ids` and `skill_policy` (explicit/auto/restricted) in the research specification; NumericOS checks trust and compatibility and returns a resolved manifest or typed incompatibility error **before** allocating expensive compute.
- On each delegated subtask, install/supply approved canonical skill revisions to its chosen provider through `AgentAdapter.install_skills`. Record per-step skill manifest hashes and what was actually supported. No silent dropping or replacement of skill instructions.
- Cross-provider handoff transmits structured hypothesis/context/evidence, not entire hidden transcripts; switching provider mid-campaign must not silently alter scientific protocol or thresholds.
- Include end-to-end parity smoke test: same canonical `scientific-method` skill loaded through at least two providers, with runtime event evidence of actual discovery. Behavioral outputs need not be identical across models; explicitly distinguish loader parity from quality parity.


## 4. Workflow and multiagent programming

Offer code-first workflow **before** elaborate graph editing. Minimum declarative transitions:

```yaml
workflow:
  id: solver-study
  steps:
    - id: propose
      actor: scientist
      action: propose_hypothesis
    - id: implement
      actor: coder
      action: implement_candidate
    - id: run
      actor: runtime
      action: execute_experiment
    - id: review
      actor: validator
      action: evaluate_result
  edges:
    - {from: propose, to: implement}
    - {from: implement, to: run}
    - {from: run, to: review}
    - {from: review, to: propose, condition: continue_search}
```

Agent role scheduling is optional and bounded. Conditions must be explicit predicates over structured state, **not** arbitrary LLM-generated Python executed blindly. Implement cycle/termination validation, branch/fan-out/join semantics when needed, concurrency limits, ownership and message contracts. Define which data are exchanged (`Hypothesis`, `RunSummary`, `DecisionRecord`, `ContextSnapshot`), not only 'Anna tells Luca something'.

A graph editor using React Flow should map to the **same validated workflow schema**, no separate browser-only execution semantics. Show two distinct graphs:
- **Planned workflow graph:** programmable agent/tool steps and conditions, optionally editable.
- **Evidence/research graph:** historical hypotheses/experiments/observations/decisions; mostly navigational/replay, never misrepresented as executable workflow.

GUI for multiagent sessions: agent role/current step, input context digest, outbound requests, decision rationale as explicitly logged, trace links, active job/resource budget, event timeline and approvals. Expand actual messages on demand; don't revert to unstructured walls of transcripts.

## 5. HPC / SLURM adapter (optional after external CLI contract)

Implement job adapter using available `sbatch`, `squeue`, `sacct`, `scancel`, scheduler logs and storage. Capture SLURM job ID, allocation, partition, requested/actual memory/time/GPUs when exposed and immutable run spec. Correctly interpret jobs queued, running, completed, failed, timed out, preempted or unknown; no false RAM/VRAM figures if accounting disabled. Supports remote shared paths or artifact transport with checksum validation. Preserve baseline comparability when hardware/partition differs. If SLURM unreachable, CLI/API reports explicit infrastructure error, not 'no jobs'.

Multiple projects/agents must have fair quotas, max parallel jobs and the ability to cancel only jobs owned by their authorized campaign.

## 6. Cross-agent concurrency and security

- Distinct isolated worktrees per concurrent code-editing hypothesis, conflict check on integration; read-only shared source where possible.
- Project / research ownership token and per-task delegated capabilities. Parent cannot grant child more compute/spend/destructive permissions than parent was granted.
- Idempotent commands; optimistic lock/version on experiment contract updates; agent cannot amend a running Run's frozen parameters; create revision and new run/cohort instead.
- No double supervisor: NumericOS alone owns run lifecycle for delegated campaign. External parent can request actions through API but does not mutate NumericOS database/processes behind its back.
- No automatic force push/merge, credential export, arbitrary remote code execution or secret logging. Remote/multiuser execution must add authenticated authorization and real sandbox boundaries before launch.
- Event trace can contain sensitive user data. Define redaction/retention and access control, especially when connecting external orchestrators or remote SLURM.

## 7. Work tickets (in value order)

1. **M5-T01 — External delegation API:** typed async request/result, idempotency, errors, capabilities, resumable events, contract tests.
2. **M5-T02 — Full CLI & Python SDK:** parity with HTTP, JSONL follow, stdout/stderr discipline, caller exits while supervisor continues; example external Python agent.
3. **M5-T03 — Concurrency:** two distinct parent/child tasks, safe worktree/job isolation, quotas, job ownership, conflict-rejection tests.
4. **M5-T04 — Agent interoperability:** add Claude Agent SDK and Pi RPC as real adapters after the initial Codex App Server slice, then OpenCode optionally; verify skills installation, event/approval translation and cross-provider context consistency with the same canonical skill digests. No mandatory MCP.
5. **M5-T05 — Code-first workflow engine:** role/step contracts, explicit graph transitions and stoppability. Benchmark one agent vs roles with same budget.
6. **M5-T06 — Workflow editor & replay:** React Flow binding to validated schema, historical research/evidence graph and unified traces/UI.
7. **M5-T07 — Optional interoperability/HPC:** MCP/A2A transport wrappers and/or SLURM backend, only after clear test case; document exact support matrix.

## 8. Acceptance tests / demo scenario

**Delegation E2E:** Parent script invokes `numericos research submit spec.yaml --json`, parses ID and exits; NumericOS worker actually runs research; hours later (simulate elapsed/detach in tests) a fresh parent process calls `status/events/results` and retrieves durable structured verdict and artifacts. No full chat transcript needed.

**Multiple independent callers:** two agent clients submit work on same repo with separate worktrees; concurrent tasks do not overwrite each other's code/metrics/status. One caller cancels its job, other continues correctly.

**Replay and recovery:** lose SSE/HTTP connection; reconnect from cursor and get ordered missed events with no false completed state; client can safely dedupe repeated delivery.

**Protocol review:** external scientist proposes change to validation threshold during running campaign; NumericOS creates reviewable new protocol version/cohort; earlier runs remain unmodified/comparable only where appropriate.

**Multiagent value:** benchmark single agent and scientist/coder/reviewer workflow with same model family/tokens/resources. If no useful gain, ship single-agent mode as default and keep multiagent feature opt-in.

**SLURM:** if implemented, queue, complete, time out and cancel real/simulated scheduler jobs; distinguish accounting unavailable from zero usage.

**CLI+GUI parity:** board/timeline/experiment state seen by agent via JSON must match GUI and recorded event ledger. No browser-specific hidden decisions.

## 9. Cross-system benchmark and outcome measures

A) chosen coding agent alone; B) **same model/provider** + computational scientific skills/tools; C) B + NumericOS runtime; D) C with optional multiagent execution. Same evaluator, budget and independent numerical task set. Also a separate human usability test of anchored Q&A/board/context against linear chat (time to find past decisions, missed constraints, number of navigation steps and trust in trace). Report uncertainty, compute costs and failure classes; don't overinterpret a tiny benchmark. Validate external orchestration reliability (idempotent submit, reconnect, no orphan jobs, provenance).

## 10. Out of scope unless separately approved

Multi-tenant SaaS billing, GPU cluster provisioning, complete A2A/MCP compatibility irrespective of client, autonomous wet-lab protocol execution, agent algebra or full drag/drop programming language, automatic scientific discovery guarantees, live shared multi-user editor and broad insecure execution of unknown code.

## 11. Exit gate

A separate research agent reliably treats NumericOS as a tool/sub-agent via **CLI or API**, delegates a computational campaign asynchronously, inspects intermediate scientific evidence and retrieves a structured result after its own session ended. GUI shows the same causal timeline and evolving scientific board. Optional multiple specialist agents follow explicitly programmed steps without competing controllers. No protocol lock-in, no silent invalid conclusions or merges.
