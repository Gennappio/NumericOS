import { describe, expect, it } from "vitest"
import type { MetricBucket, MetricOverview } from "@/api/client"
import { chartData } from "./metricChart"

function bucket(overrides: Partial<MetricBucket>): MetricBucket {
  return {
    samples: 1,
    non_finite: 0,
    first_step: null,
    last_step: null,
    first_time: null,
    last_time: null,
    first_t: 0,
    last_t: 0,
    first_value: 1,
    last_value: 1,
    min_value: 1,
    max_value: 1,
    ...overrides,
  }
}

const overview = (...buckets: MetricBucket[]): MetricOverview => ({
  name: "residual",
  samples: buckets.reduce((total, item) => total + item.samples, 0),
  buckets,
  next_cursor: 0,
  complete: true,
})

describe("chartData", () => {
  it("places samples at their step when the steps only increase", () => {
    const data = chartData(
      overview(bucket({ last_step: 0, last_value: 1 }), bucket({ last_step: 10, last_value: 0.5 })),
    )

    expect(data.xLabel).toBe("step")
    expect(data.points).toEqual([
      { x: 0, y: 1, low: undefined, high: undefined },
      { x: 10, y: 0.5, low: undefined, high: undefined },
    ])
  })

  it("falls back to the position in the series when steps are missing or go back", () => {
    const withoutSteps = chartData(overview(bucket({ samples: 3 }), bucket({ samples: 2 })))
    const restarted = chartData(overview(bucket({ last_step: 50 }), bucket({ last_step: 10 })))

    expect(withoutSteps.xLabel).toBe("sample")
    expect(withoutSteps.points.map((point) => point.x)).toEqual([3, 5]) // samples seen so far
    expect(restarted.xLabel).toBe("sample")
  })

  it("keeps the extremes of a stretch that stands for several samples", () => {
    const data = chartData(
      overview(bucket({ samples: 40, last_step: 400, last_value: 0.2, min_value: 0.1, max_value: 9 })),
    )

    expect(data.points[0]).toEqual({ x: 400, y: 0.2, low: 0.1, high: 9 })
  })

  it("marks where samples are not finite and leaves the line open there", () => {
    const data = chartData(
      overview(
        bucket({ last_step: 10, last_value: 0.5 }),
        bucket({ last_step: 20, last_value: null, non_finite: 1, min_value: null, max_value: null }),
        bucket({ samples: 5, last_step: 70, last_value: 0.1, non_finite: 2 }),
      ),
    )

    expect(data.points[1].y).toBeNull()
    expect(data.marks).toEqual([
      { x: 20, label: "a sample not finite at step 20" },
      { x: 70, label: "2 samples not finite at step 70" },
    ])
  })
})
