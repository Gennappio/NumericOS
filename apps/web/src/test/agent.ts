import type { AgentCapabilities, AgentSession, Message } from "@/api/client"

/** Records of conversations as the API returns them; a test overrides what it cares about. */

export function capabilitiesRecord(overrides: Partial<AgentCapabilities> = {}): AgentCapabilities {
  return {
    provider: "claude_code",
    command: ["claude"],
    available: true,
    path: "/usr/local/bin/claude",
    version: "2.1.296 (Claude Code)",
    problem: null,
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
    model: null,
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
    model: null,
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
    model: "claude-fable-5-1",
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
