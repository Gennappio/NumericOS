import { describe, expect, it } from "vitest"
import type { Card, WorkflowStatus } from "@/api/client"
import { placementOfDrop } from "./boardDrop"

function card(id: string, status: WorkflowStatus, order: number): Card {
  return {
    id,
    project_id: "prj_1",
    type: "task",
    title: id,
    description: "",
    workflow_status: status,
    sort_order: order,
    entity_ref: null,
    origin: "user",
    version: 1,
    created_at: "2026-10-12T10:00:00Z",
    updated_at: "2026-10-12T10:00:00Z",
  }
}

const CARDS = [
  card("a", "backlog", 0),
  card("b", "backlog", 1000),
  card("c", "backlog", 2000),
  card("x", "active", 0),
]

describe("placementOfDrop", () => {
  it("takes the place of the card it is dropped on, inside its column", () => {
    expect(placementOfDrop(CARDS, "a", "c")).toEqual({ position: 2 })
    expect(placementOfDrop(CARDS, "c", "a")).toEqual({ position: 0 })
  })

  it("moves to another column at the place of the card it is dropped on", () => {
    expect(placementOfDrop(CARDS, "a", "x")).toEqual({ workflow_status: "active", position: 0 })
  })

  it("goes to the end of a column it is dropped on", () => {
    expect(placementOfDrop(CARDS, "a", "column:review")).toEqual({ workflow_status: "review" })
    expect(placementOfDrop(CARDS, "a", "column:backlog")).toEqual({ position: 2 })
  })

  it("is nothing when dropped where it already is", () => {
    expect(placementOfDrop(CARDS, "a", "a")).toBeNull()
    expect(placementOfDrop(CARDS, "c", "column:backlog")).toBeNull()
    expect(placementOfDrop(CARDS, "missing", "a")).toBeNull()
    expect(placementOfDrop(CARDS, "a", "gone")).toBeNull()
  })
})
