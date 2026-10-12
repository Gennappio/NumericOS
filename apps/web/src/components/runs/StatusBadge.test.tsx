import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { RunStatus } from "@/api/client"
import { RUN_STATUS_LABELS } from "@/lib/runs"
import { StatusBadge } from "./StatusBadge"

describe("StatusBadge", () => {
  it("words a normal end as a fact about the process, without the colour of success", () => {
    render(<StatusBadge status="succeeded" />)

    const badge = screen.getByText("Ended normally")
    expect(badge).toHaveAttribute("data-status", "succeeded")
    expect(badge.className).not.toMatch(/green|emerald/)
    expect(badge).toHaveAttribute("title", expect.stringContaining("says nothing about its result"))
  })

  it("has a label for every status of the contract", () => {
    for (const status of Object.keys(RUN_STATUS_LABELS) as RunStatus[]) {
      const { unmount } = render(<StatusBadge status={status} />)
      expect(screen.getByText(RUN_STATUS_LABELS[status])).toBeVisible()
      unmount()
    }
    expect(RUN_STATUS_LABELS.lost).toBe("Lost")
  })
})
