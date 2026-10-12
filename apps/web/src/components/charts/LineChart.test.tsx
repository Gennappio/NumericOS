import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { LineChart } from "./LineChart"

const part = (container: HTMLElement, name: string) =>
  container.querySelectorAll(`[data-part="${name}"]`)

describe("LineChart", () => {
  it("draws a line through the samples and says what it shows", () => {
    const { container } = render(
      <LineChart
        label="l2_error over step"
        xLabel="step"
        points={[
          { x: 0, y: 0 },
          { x: 10, y: 0.5 },
          { x: 20, y: 1 },
        ]}
      />,
    )

    expect(screen.getByRole("img", { name: "l2_error over step: 3 points, step 0 to 20" })).toBeVisible()
    const line = part(container, "line")[0].getAttribute("d")!
    expect(line.match(/[ML]/g)).toEqual(["M", "L", "L"])
    expect(line.startsWith("M64.00,188.00")).toBe(true) // the first sample at the origin of the plot
    expect(line.endsWith("L628.00,14.00")).toBe(true) // the last one at its top right corner
  })

  it("breaks the line at a sample that is not finite and marks it", () => {
    const { container } = render(
      <LineChart
        label="residual over step"
        xLabel="step"
        points={[
          { x: 1, y: 0.5 },
          { x: 2, y: 0.25 },
          { x: 3, y: null },
          { x: 4, y: 0.1 },
          { x: 5, y: 0.05 },
        ]}
        marks={[{ x: 3, label: "NaN at step 3" }]}
      />,
    )

    const line = part(container, "line")[0].getAttribute("d")!
    expect(line.match(/M/g)).toHaveLength(2) // two separate strokes, nothing drawn across step 3
    expect(part(container, "non-finite")).toHaveLength(1)
    expect(screen.getByText("NaN at step 3")).toBeInTheDocument()
    expect(screen.getByText(/A red mark is a sample that is not finite/)).toBeVisible()
  })

  it("leaves values without a logarithm out of a logarithmic axis and counts them", () => {
    const { container } = render(
      <LineChart
        label="l2_error over step"
        xLabel="step"
        scale="log"
        points={[
          { x: 0, y: 0 },
          { x: 10, y: 1e-6 },
          { x: 20, y: 1e-4 },
        ]}
      />,
    )

    expect(part(container, "line")[0].getAttribute("d")!.match(/[ML]/g)).toEqual(["M", "L"])
    expect(screen.getByText(/1 value that is not positive cannot be shown on it/)).toBeVisible()
    expect(screen.getByText("1e-6")).toBeInTheDocument() // powers of ten on the axis
  })

  it("draws the extremes of each stretch as a band and the contract's bound as a line", () => {
    const { container } = render(
      <LineChart
        label="max_abs_u over step"
        xLabel="step"
        points={[
          { x: 0, y: 0.9, low: 0.8, high: 1.0 },
          { x: 100, y: 0.5, low: 0.4, high: 0.9 },
        ]}
        thresholds={[{ value: 1.0, label: "above 1 stops the run" }]}
      />,
    )

    expect(part(container, "band")).toHaveLength(1)
    expect(part(container, "threshold")).toHaveLength(1)
    expect(screen.getByText("above 1 stops the run")).toBeInTheDocument()
  })

  it("says so when there is nothing finite to draw", () => {
    const { container } = render(
      <LineChart label="energy over step" xLabel="step" points={[{ x: 0, y: null }]} />,
    )

    expect(
      screen.getByRole("img", { name: "energy over step: no finite sample to draw" }),
    ).toBeVisible()
    expect(part(container, "line")).toHaveLength(0)
  })
})
