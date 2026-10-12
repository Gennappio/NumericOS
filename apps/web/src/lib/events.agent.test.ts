import { describe, expect, it } from "vitest"
import { ledgerEvent } from "@/test/events"
import { describeEvent } from "./events"

describe("describeEvent for conversations with the agent", () => {
  it("names the turn events from their own payload", () => {
    expect(describeEvent(ledgerEvent(1, { type: "AGENT_SESSION_STARTED", payload: {} }))).toBe(
      "Conversation with the agent opened",
    )
    expect(
      describeEvent(
        ledgerEvent(2, {
          type: "AGENT_TURN_QUEUED",
          payload: { prompt_excerpt: "Why is the scheme unstable?" },
        }),
      ),
    ).toBe('Agent asked: "Why is the scheme unstable?"')
    expect(
      describeEvent(ledgerEvent(3, { type: "AGENT_TURN_STARTED", payload: { pid: 4242 } })),
    ).toBe("Agent working (process 4242)")
    expect(
      describeEvent(
        ledgerEvent(4, {
          type: "AGENT_TURN_FINISHED",
          payload: { status: "final", status_reason: null },
        }),
      ),
    ).toBe("Agent turn ended, answered")
    expect(
      describeEvent(
        ledgerEvent(5, {
          type: "AGENT_TURN_FINISHED",
          payload: { status: "cancelled", status_reason: "seen enough" },
        }),
      ),
    ).toBe("Agent turn ended, stopped: seen enough")
    expect(
      describeEvent(
        ledgerEvent(6, { type: "AGENT_TURN_CANCEL_REQUESTED", payload: { reason: "typo" } }),
      ),
    ).toBe("Stop requested: typo")
    expect(
      describeEvent(
        ledgerEvent(7, {
          type: "AGENT_SESSION_UPDATED",
          payload: { changed_fields: ["title", "permission_mode"] },
        }),
      ),
    ).toBe("Conversation changed: title, permission_mode")
  })
})
