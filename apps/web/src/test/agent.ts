import type {
  AgentCapabilities,
  AgentPolicy,
  AgentSession,
  Annotation,
  DocumentOut,
  FileEntry,
  Message,
} from "@/api/client"

/** Records of conversations as the API returns them; a test overrides what it cares about. */

export function capabilitiesRecord(overrides: Partial<AgentCapabilities> = {}): AgentCapabilities {
  return {
    provider: "claude_code",
    command: ["claude"],
    available: true,
    path: "/usr/local/bin/claude",
    version: "2.1.296 (Claude Code)",
    problem: null,
    models: [
      { id: "claude-fable-5-1", label: "Fable 5.1", note: "most capable; the heaviest" },
      { id: "claude-sonnet-5-5", label: "Sonnet 5.5", note: "fast; a fraction of Fable" },
      { id: "claude-haiku-5-5", label: "Haiku 5.5", note: "lightest" },
    ],
    efforts: ["low", "medium", "high", "xhigh", "max"],
    ...overrides,
  }
}

export function policyRecord(overrides: Partial<AgentPolicy> = {}): AgentPolicy {
  const none = { model: null, effort: null }
  return {
    project_id: "prj_1",
    provider: "claude_code",
    defaults: none,
    provider_default: null,
    tasks: {
      conversation: { model: "claude-sonnet-5-5", effort: "medium" },
      clarify: none,
      resolve: none,
      theory: none,
      file_description: { model: "claude-haiku-5-5", effort: "low" },
      pipeline: none,
      plan: none,
    },
    available: ["conversation"],
    version: 1,
    updated_at: "2026-10-12T09:30:00Z",
    ...overrides,
  }
}

export function sessionRecord(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: "ases_1",
    project_id: "prj_1",
    title: "Why is the explicit scheme unstable?",
    provider: "claude_code",
    permission_mode: "edit",
    task: "conversation",
    model: null,
    effort: null,
    native_session_id: "0d5a2c4e-1b2f-4c6d-9e8f-123456789abc",
    cwd: "/work/heat2d",
    message_count: 2,
    version: 2,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:05Z",
    ...overrides,
  }
}

export function userMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg_user",
    session_id: "ases_1",
    project_id: "prj_1",
    role: "user",
    status: "final",
    status_reason: null,
    markdown: "Why is the explicit scheme unstable?",
    prompt_message_id: null,
    model_requested: null,
    effort: null,
    model: null,
    plan_usage: null,
    activity: [],
    activity_dropped: 0,
    files_read: [],
    files_written: [],
    files_created: [],
    files_moved: [],
    permission_denials: [],
    cost_usd: null,
    usage: null,
    num_turns: null,
    structured_output: null,
    worker_id: null,
    pid: null,
    exit_code: null,
    started_at: null,
    finished_at: null,
    cancel_requested_at: null,
    cancel_reason: null,
    version: 1,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:00Z",
    ...overrides,
  }
}

export function answerRecord(overrides: Partial<Message> = {}): Message {
  return {
    ...userMessage(),
    id: "msg_answer",
    role: "assistant",
    status: "final",
    markdown:
      "Because the explicit scheme is only conditionally stable: it needs\n\n" +
      "$$\\frac{\\alpha\\,\\Delta t}{\\Delta x^2} \\le \\frac{1}{2}.$$",
    prompt_message_id: "msg_user",
    model_requested: "claude-fable-5-1",
    effort: "high",
    model: "claude-fable-5-1",
    plan_usage: {
      five_hour: { utilization: 0.21, resets_at: 1791835200 },
      seven_day: { utilization: 0.04, resets_at: 1792429200 },
      using_overage: false,
    },
    activity: [
      { kind: "text", at: 1.0, text: "I'll read the solver first.", tool: null },
      {
        kind: "tool",
        at: 1.5,
        text: null,
        tool: { id: "toolu_1", name: "Read", summary: "/work/heat2d/heat2d.py", ok: true },
      },
    ],
    files_read: ["heat2d.py"],
    cost_usd: 0.0123,
    usage: {
      input_tokens: 12,
      output_tokens: 34,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 5,
    },
    num_turns: 2,
    worker_id: "wrk_1",
    pid: 4242,
    exit_code: 0,
    started_at: "2026-10-12T10:00:01Z",
    finished_at: "2026-10-12T10:00:04Z",
    version: 3,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:04Z",
    ...overrides,
  }
}

export function documentRecord(overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: "doc_1",
    project_id: "prj_1",
    kind: "theory",
    key: "theory",
    title: "Explicit scheme for the 2D heat equation",
    summary: "",
    category: null,
    markdown:
      "# Explicit scheme for the 2D heat equation\n\n## Model\n\n$$u_t = \\alpha \\nabla^2 u \\tag{1}$$\n\n" +
      "![The grid](docs/grid.png)\n",
    status: "ready",
    status_reason: null,
    instructions: "Scrivi in italiano.",
    sources: [
      { path: "heat2d.py", sha: "aaa" },
      { path: "docs/notes.md", sha: "bbb" },
    ],
    session_id: "ases_theory",
    message_id: "msg_theory",
    pending_message_id: null,
    model: "claude-fable-5-1",
    generated_at: "2026-10-12T10:00:04Z",
    version: 1,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:04Z",
    stale: false,
    changed_sources: [],
    ...overrides,
  }
}

/**
 * A pipeline of three boxes. Its text is put together as the API does: the title, the
 * summary, then a section per box, each box naming its range in code points (the emoji of
 * the title counts once there, and twice where JavaScript indexes the string).
 */
export function pipelineRecord(overrides: Partial<DocumentOut> = {}): DocumentOut {
  const boxes = [
    {
      id: "parameters",
      kind: "input" as const,
      title: "Read the parameters",
      body: "The run starts from `experiment.yaml`: the grid size and $\\alpha$.",
      files: ["examples/experiment.yaml"],
      repeats: null,
    },
    {
      id: "time-loop",
      kind: "process" as const,
      title: "Advance in time",
      body:
        "The explicit scheme updates every point from its four neighbours.\n\n" +
        "- stable when $r \\le 1/4$\n- first order in time",
      files: ["heat2d.py", "src/stencil.py"],
      repeats: "every time step",
    },
    {
      id: "results",
      kind: "output" as const,
      title: "Write the results",
      body: "The final field goes to the run directory.",
      files: [],
      repeats: null,
    },
  ]
  let markdown =
    "# Pipeline of the 2D heat solver 😀\n\n" +
    "One run reads its parameters, advances the scheme and writes the final field."
  const nodes = boxes.map(({ body, ...box }) => {
    const start = [...markdown].length + 2
    markdown += `\n\n## ${box.title}\n\n${body}`
    return { ...box, start, end: [...markdown].length }
  })
  return documentRecord({
    id: "doc_p",
    kind: "pipeline",
    key: "pipeline",
    title: "Pipeline of the 2D heat solver 😀",
    summary: "One run reads its parameters, advances the scheme and writes the final field.",
    markdown,
    pipeline: {
      nodes,
      edges: [
        { source: "parameters", target: "time-loop", label: "n, alpha, dt" },
        { source: "time-loop", target: "results", label: "" },
      ],
    },
    sources: [
      { path: "heat2d.py", sha: "aaa" },
      { path: "examples/experiment.yaml", sha: "bbb" },
    ],
    instructions: "",
    session_id: "ases_pipeline",
    message_id: "msg_pipeline",
    model: "claude-sonnet-5-5",
    ...overrides,
  })
}

export function fileRecord(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    path: "src/heat2d.py",
    size_bytes: 2048,
    category: "code",
    sha: "aaa",
    viewable_image: false,
    description: {
      document_id: "doc_f1",
      status: "ready",
      summary: "The explicit solver of the heat equation.",
      stale: false,
      pending: false,
      status_reason: null,
      updated_at: "2026-10-12T10:00:04Z",
    },
    ...overrides,
  }
}

export function annotationRecord(overrides: Partial<Annotation> = {}): Annotation {
  return {
    id: "ann_1",
    project_id: "prj_1",
    target_type: "document",
    target_id: "doc_1",
    target_version: 1,
    kind: "clarification",
    status: "open",
    status_reason: null,
    body: "Why?",
    start_offset: 0,
    end_offset: 1,
    quote: "x",
    prefix: "",
    suffix: "",
    anchor_state: "attached",
    response_markdown: null,
    message_id: null,
    pending_message_id: null,
    responded_at: null,
    version: 1,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:00Z",
    ...overrides,
  }
}
