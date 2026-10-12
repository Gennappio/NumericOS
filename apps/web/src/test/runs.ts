import type { Experiment, Project, Run, RunMetrics, SeriesSummary } from "@/api/client"

/** Records as the API returns them; a test overrides what it cares about. */

export function projectRecord(overrides: Partial<Project> = {}): Project {
  return {
    id: "prj_1",
    name: "Heat 2D",
    research_question: "",
    description: "",
    root_path: "/work/heat2d",
    is_demo: false,
    execution_trusted_at: "2026-10-12T09:00:00Z",
    version: 2,
    created_at: "2026-10-12T08:00:00Z",
    updated_at: "2026-10-12T09:00:00Z",
    ...overrides,
  }
}

export function runRecord(overrides: Partial<Run> = {}): Run {
  return {
    id: "run_1",
    project_id: "prj_1",
    experiment_id: "exp_1",
    label: "",
    status: "succeeded",
    status_reason: null,
    failure_class: null,
    parameters: { grid: 32, dt: 0.0002 },
    seed: null,
    argv: ["python3", "heat2d.py", "--dt", "0.0002"],
    protocol_digest: "5e2d4ea119060600d0c1a960cdd4d3b86bfa9ce18074e7b453fea83d4e58d3e3",
    code: {
      mode: "ref",
      repository_root: "/work/heat2d",
      requested_ref: "HEAD",
      sha: "4aa50e95d0a23bfda59524130db214e6dec63a29",
      commit: { subject: "solver", author: "Ada Lovelace", authored_at: "2026-10-12T09:00:00Z" },
      dirty: false,
      submitted_with_dirty_working_tree: false,
    },
    inputs: [],
    environment: null,
    reproduces_run_id: null,
    worker_id: "wrk_1",
    pid: 4242,
    started_at: "2026-10-12T10:00:00Z",
    finished_at: "2026-10-12T10:00:01Z",
    heartbeat_at: "2026-10-12T10:00:01Z",
    cancel_requested_at: null,
    cancel_reason: null,
    exit_code: 0,
    exit_signal: null,
    wall_seconds: 1.2,
    outcome: null,
    resources: null,
    version: 3,
    created_at: "2026-10-12T09:59:59Z",
    updated_at: "2026-10-12T10:00:01Z",
    ...overrides,
  }
}

export function seriesRecord(name: string, overrides: Partial<SeriesSummary> = {}): SeriesSummary {
  return {
    name,
    unit: "1",
    source: "instrumentation",
    declared: true,
    samples: 61,
    non_finite: 0,
    stored: 61,
    first_value: 1,
    first_step: 0,
    last_value: 0.09,
    last_non_finite: null,
    last_step: 600,
    last_time: 0.12,
    last_at: 1_800_000_000,
    min_value: 0.09,
    max_value: 1,
    ...overrides,
  }
}

export function metricsRecord(overrides: Partial<RunMetrics> = {}): RunMetrics {
  return {
    series: [],
    coverage: {
      levels: [
        { level: "L0", title: "Process", status: "observed", detail: "exit status and output" },
        { level: "L1", title: "Output parsers", status: "not_configured", detail: "no parser" },
        { level: "L2", title: "Instrumentation", status: "observed", detail: "2 of 2 metrics" },
        {
          level: "L3",
          title: "Validators",
          status: "not_configured",
          detail: "no validator is configured: nothing here says whether the result is valid",
        },
      ],
      metrics: [],
      undeclared: [],
    },
    records: 0,
    parsed_lines: 0,
    program_events: 0,
    truncated: false,
    diagnostics: [],
    ...overrides,
  }
}

export function experimentRecord(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: "exp_1",
    project_id: "prj_1",
    hypothesis_id: null,
    name: "heat2d-stability",
    protocol: {
      schema: "numericos.experiment.v1",
      question: "Does the scheme stay bounded below its stability limit?",
      independent_variables: { dt: [0.0002, 0.0003] },
      controls: { grid: 32 },
      execution: { command: ["python3", "heat2d.py", "--dt", "{dt}"] },
      metrics: [{ name: "max_abs_u", unit: "1", sampled_by: "instrumentation" }],
      guardrails: {
        non_finite: "halt",
        rules: [{ metric: "max_abs_u", above: 1, patience: 3, action: "halt" }],
      },
      limits: { wall_seconds: 120 },
    },
    protocol_digest: "5e2d4ea119060600d0c1a960cdd4d3b86bfa9ce18074e7b453fea83d4e58d3e3",
    run_count: 1,
    version: 1,
    created_at: "2026-10-12T09:00:00Z",
    updated_at: "2026-10-12T09:00:00Z",
    ...overrides,
  }
}
