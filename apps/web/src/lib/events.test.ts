import { describe, expect, it } from "vitest"
import { ledgerEvent } from "@/test/events"
import { describeEvent } from "./events"

const card = { title: "H01", workflow_status: "review" }

describe("describeEvent", () => {
  it("names project events and the fields that changed", () => {
    expect(describeEvent(ledgerEvent(1, { type: "PROJECT_CREATED", payload: {} }))).toBe(
      "Project created",
    )
    expect(
      describeEvent(
        ledgerEvent(2, {
          type: "PROJECT_UPDATED",
          payload: { changed_fields: ["name", "research_question", "root_path"] },
        }),
      ),
    ).toBe("Project updated: name, research question, code path")
  })

  it("says where a card was created and what was edited", () => {
    expect(describeEvent(ledgerEvent(3, { type: "CARD_CREATED", payload: { card } }))).toBe(
      'Card created: "H01" in Review',
    )
    expect(
      describeEvent(
        ledgerEvent(4, {
          type: "CARD_UPDATED",
          payload: { card, changed_fields: ["title", "description"] },
        }),
      ),
    ).toBe('Card edited: "H01" (title, description)')
  })

  it("tells a move between columns from a reorder inside one", () => {
    const moved = ledgerEvent(5, {
      type: "CARD_MOVED",
      payload: {
        card,
        changed_fields: [],
        from: { workflow_status: "backlog", sort_order: 0 },
        to: { workflow_status: "review", sort_order: 1000 },
      },
    })
    const reordered = ledgerEvent(6, {
      type: "CARD_MOVED",
      payload: {
        card,
        changed_fields: ["title"],
        from: { workflow_status: "review", sort_order: 1000 },
        to: { workflow_status: "review", sort_order: 0 },
      },
    })

    expect(describeEvent(moved)).toBe('Card moved: "H01" from Backlog to Review')
    expect(describeEvent(reordered)).toBe('Card reordered: "H01" in Review, edited title')
  })

  it("shows an unknown event type as recorded instead of interpreting it", () => {
    const future = ledgerEvent(7, { type: "VERDICT_RECORDED", subject_id: "run_1", payload: {} })

    expect(describeEvent(future)).toBe("VERDICT_RECORDED")
  })

  it("describes what happened to a run from the event's own payload", () => {
    const of = (type: string, payload: Record<string, unknown>) =>
      describeEvent(ledgerEvent(9, { type, payload }))

    expect(of("RUN_QUEUED", { run: {} })).toBe("Run queued")
    expect(of("RUN_STARTED", { pid: 4242 })).toBe("Program started (process 4242)")
    expect(of("RUN_CANCEL_REQUESTED", { reason: "wrong mesh" })).toBe("Stop requested: wrong mesh")
    expect(of("RUN_LIMIT_EXCEEDED", { limit: "wall_seconds", value: 60.2, threshold: 60 })).toBe(
      "Limit passed: wall_seconds reached 60.2, allowed 60",
    )
    expect(of("RUN_METRIC_NON_FINITE", { metric: "residual", value: "nan", step: 12 })).toBe(
      "Metric residual became NaN at step 12",
    )
    expect(
      of("RUN_GUARDRAIL_VIOLATED", {
        metric: "max_abs_u",
        bound: "above",
        threshold: 1,
        value: 4776.120262943853,
        non_finite: null,
        step: 130,
        consecutive: 3,
        action: "halt",
      }),
    ).toBe(
      "Guardrail: max_abs_u above 1 for 3 consecutive samples (4776.12 at step 130); the program was stopped",
    )
    expect(of("RUN_PROGRAM_EVENT", { name: "restart", message: "time step halved", step: 120 })).toBe(
      "Program: restart: time step halved at step 120",
    )
    expect(of("EXPERIMENT_CREATED", { experiment: { name: "heat2d-stability" } })).toBe(
      'Experiment defined: "heat2d-stability"',
    )
  })

  it("never words a normal end of the process as a valid result", () => {
    const ended = describeEvent(
      ledgerEvent(10, { type: "RUN_FINISHED", payload: { status: "succeeded", status_reason: null } }),
    )
    const failed = describeEvent(
      ledgerEvent(11, {
        type: "RUN_FINISHED",
        payload: { status: "failed", status_reason: "the program exited with code 3" },
      }),
    )

    expect(ended).toBe("Run ended, ended normally")
    expect(ended).not.toMatch(/valid|success|pass/i)
    expect(failed).toBe("Run ended, failed: the program exited with code 3")
  })

  it("falls back to the subject ID when the payload carries no card", () => {
    const bare = ledgerEvent(8, { type: "CARD_UPDATED", subject_id: "card_9", payload: {} })

    expect(describeEvent(bare)).toBe("Card edited: card_9")
  })
})
