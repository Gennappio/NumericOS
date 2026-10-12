import type { AgentCapabilities, AgentPolicy, AgentSession, Message } from "@/api/client"

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
    tasks: {
      conversation: { model: "claude-sonnet-5-5", effort: "medium" },
      clarify: none,
      resolve: none,
      theory: none,
      file_description: { model: "claude-haiku-5-5", effort: "low" },
      execution_description: none,
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
