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
    ).toBe("Project updated: name, research question, code reference")
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
    const future = ledgerEvent(7, { type: "RUN_STARTED", subject_id: "run_1", payload: {} })

    expect(describeEvent(future)).toBe("RUN_STARTED")
  })

  it("falls back to the subject ID when the payload carries no card", () => {
    const bare = ledgerEvent(8, { type: "CARD_UPDATED", subject_id: "card_9", payload: {} })

    expect(describeEvent(bare)).toBe("Card edited: card_9")
  })
})
