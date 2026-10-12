import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ledgerEvent } from "@/test/events"
import { EventStrip } from "./EventStrip"

const page = {
  events: [
    ledgerEvent(12, {
      type: "CARD_MOVED",
      actor: "cli:local",
      payload: {
        card: { title: "H01", workflow_status: "review" },
        changed_fields: [],
        from: { workflow_status: "backlog" },
        to: { workflow_status: "review" },
      },
    }),
    ledgerEvent(9, { payload: { card: { title: "H01", workflow_status: "backlog" } } }),
    ledgerEvent(4, { type: "PROJECT_CREATED", subject_id: "prj_1", payload: {} }),
  ],
  next_cursor: 4,
  has_more: false,
}

describe("EventStrip", () => {
  it("lists the recorded events in the order given, with position, text and actor", () => {
    render(<EventStrip projectId="prj_1" page={page} transport="live" />)

    const rows = within(screen.getByRole("region", { name: "Recent events" })).getAllByRole(
      "listitem",
    )
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringMatching(/^#12.*Card moved: "H01" from Backlog to Review.*cli:local$/),
      expect.stringMatching(/^#9.*Card created: "H01" in Backlog.*web:local$/),
      expect.stringMatching(/^#4.*Project created.*web:local$/),
    ])
  })

  it("says whether updates are live or the page is polling", () => {
    const { rerender } = render(<EventStrip projectId="prj_1" page={page} transport="live" />)
    const status = screen.getByRole("status", { name: "Live updates" })
    expect(status).toHaveAttribute("data-transport", "live")
    expect(status).toHaveTextContent("Live")

    rerender(<EventStrip projectId="prj_1" page={page} transport="reconnecting" />)
    expect(status).toHaveAttribute("data-transport", "reconnecting")
    expect(status).toHaveTextContent("Live updates interrupted · refreshing every 5 s")
  })

  it("points to the CLI for older entries only when there are some", () => {
    const { rerender } = render(<EventStrip projectId="prj_1" page={page} transport="live" />)
    expect(screen.queryByText(/numericos events list/)).not.toBeInTheDocument()

    rerender(
      <EventStrip projectId="prj_1" page={{ ...page, has_more: true }} transport="live" />,
    )
    expect(screen.getByText("numericos events list --project prj_1")).toBeInTheDocument()
  })

  it("shows a loading state instead of an empty ledger while events are fetched", () => {
    render(<EventStrip projectId="prj_1" page={undefined} transport="connecting" />)

    expect(screen.getByText("Loading events…")).toBeInTheDocument()
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
  })
})
