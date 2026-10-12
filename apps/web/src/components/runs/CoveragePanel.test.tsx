import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { metricsRecord } from "@/test/runs"
import { CoveragePanel } from "./CoveragePanel"

describe("CoveragePanel", () => {
  it("shows each level with its state, and validators as not configured", () => {
    render(<CoveragePanel metrics={metricsRecord()} />)

    const rows = screen.getAllByRole("listitem")
    expect(within(rows[0]).getByText("Process")).toBeVisible()
    expect(within(rows[0]).getByText("Observed")).toBeVisible()
    expect(within(rows[3]).getByText("Validators")).toBeVisible()
    expect(within(rows[3]).getByText("Not configured")).toBeVisible()
    expect(within(rows[3]).getByText(/nothing here says whether the result is valid/)).toBeVisible()
  })

  it("never presents having data as a sign of validity", () => {
    const { container } = render(<CoveragePanel metrics={metricsRecord()} />)

    const observed = container.querySelector("[data-coverage=observed]")!
    expect(observed.className).not.toMatch(/green|emerald/)
    expect(container.textContent).not.toMatch(/passed|verified|success/i)
  })

  it("names what the contract declares and nobody measured", () => {
    const metrics = metricsRecord()
    metrics.coverage.metrics = [
      { name: "l2_error", unit: "1", source: "instrumentation", status: "observed", samples: 61, non_finite: 0 },
      { name: "energy", unit: "J", source: "parser", status: "missing", samples: 0, non_finite: 0 },
      { name: "wall_time", unit: "s", source: "supervisor", status: "waiting", samples: 0, non_finite: 0 },
    ]
    render(<CoveragePanel metrics={metrics} />)

    const missing = screen.getByText("Declared by the contract, without a sample").parentElement!
    expect(within(missing).getByText("energy")).toBeVisible()
    expect(within(missing).getByText("Missing")).toBeVisible()
    expect(within(missing).getByText("wall_time")).toBeVisible()
    expect(within(missing).getByText("Waiting")).toBeVisible()
    expect(within(missing).queryByText("l2_error")).toBeNull()
  })

  it("reports what was wrong with the program's records, with examples", () => {
    const metrics = metricsRecord({
      truncated: true,
      diagnostics: [
        {
          kind: "malformed_record",
          message: "Lines that look like NumericOS records but are not valid.",
          count: 3,
          examples: ['\'value\' must be a number: {"schema":"numericos.metric.v1"}'],
        },
      ],
    })
    metrics.coverage.undeclared = ["debug_norm"]
    render(<CoveragePanel metrics={metrics} />)

    expect(screen.getByText(/Lines that look like NumericOS records/)).toBeVisible()
    expect(screen.getByText("(3×)")).toBeVisible()
    expect(screen.getByText(/'value' must be a number/)).toBeVisible()
    expect(screen.getByText("debug_norm")).toBeVisible()
    expect(screen.getByText(/counted, not stored/)).toBeVisible()
  })
})
