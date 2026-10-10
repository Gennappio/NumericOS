import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { Card, WorkflowStatus } from "@/api/client"
import { CardItem } from "./CardItem"

const STATUSES: WorkflowStatus[] = [
  "backlog",
  "planned",
  "active",
  "review",
  "completed",
  "blocked",
]

const completedHypothesis: Card = {
  id: "card_01J9W2Z4K7QX8YB3N5M6T0R1S2",
  project_id: "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2",
  type: "hypothesis",
  title: "H01: smaller dt restores stability",
  description: "Prediction: residual growth disappears below the stability limit.",
  workflow_status: "completed",
  sort_order: 1000,
  entity_ref: null,
  version: 3,
  created_at: "2026-10-10T08:00:00Z",
  updated_at: "2026-10-10T09:00:00Z",
}

function renderCard(overrides: Partial<Parameters<typeof CardItem>[0]> = {}) {
  const onMove = vi.fn()
  const onOpen = vi.fn()
  render(
    <CardItem
      card={completedHypothesis}
      index={1}
      count={3}
      statuses={STATUSES}
      disabled={false}
      onOpen={onOpen}
      onMove={onMove}
      {...overrides}
    />,
  )
  return { onMove, onOpen }
}

describe("CardItem", () => {
  it("shows type and workflow status and never a validity verdict", () => {
    renderCard()

    const card = screen.getByRole("article", { name: completedHypothesis.title })
    expect(card).toHaveTextContent("Hypothesis")
    expect(screen.getByLabelText(/Workflow status of/)).toHaveValue("completed")
    expect(card.textContent).not.toMatch(/supported|refuted|validated|confirmed|passed/i)
  })

  it("asks to move to the chosen column", () => {
    const { onMove } = renderCard()

    fireEvent.change(screen.getByLabelText(/Workflow status of/), { target: { value: "review" } })

    expect(onMove).toHaveBeenCalledWith({ workflow_status: "review" })
  })

  it("asks to move one position up or down inside the column", () => {
    const { onMove } = renderCard()

    fireEvent.click(screen.getByRole("button", { name: /^Move .* up$/ }))
    fireEvent.click(screen.getByRole("button", { name: /^Move .* down$/ }))

    expect(onMove.mock.calls).toEqual([[{ position: 0 }], [{ position: 2 }]])
  })

  it("cannot move beyond the ends of the column", () => {
    renderCard({ index: 0, count: 1 })

    expect(screen.getByRole("button", { name: /^Move .* up$/ })).toBeDisabled()
    expect(screen.getByRole("button", { name: /^Move .* down$/ })).toBeDisabled()
  })

  it("opens the card from its title and locks every change while disabled", () => {
    const { onOpen } = renderCard({ disabled: true })

    fireEvent.click(screen.getByRole("button", { name: completedHypothesis.title }))

    expect(onOpen).toHaveBeenCalledOnce()
    expect(screen.getByLabelText(/Workflow status of/)).toBeDisabled()
    expect(screen.getByRole("button", { name: /^Move .* up$/ })).toBeDisabled()
  })
})
