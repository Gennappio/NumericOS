import { describe, expect, it } from "vitest"
import {
  bandPath,
  linearAxis,
  linearTicks,
  linePath,
  logAxis,
  logTicks,
  nearestIndex,
  segments,
  type ChartPoint,
} from "./chart"

describe("linearTicks", () => {
  it("returns round values inside the interval", () => {
    expect(linearTicks(0, 600)).toEqual([0, 200, 400, 600])
    expect(linearTicks(0, 600, 8)).toEqual([0, 100, 200, 300, 400, 500, 600])
    expect(linearTicks(0.093, 1)).toEqual([0.2, 0.4, 0.6, 0.8, 1])
    expect(linearTicks(-0.3, 0.3, 4)).toEqual([-0.2, 0, 0.2])
  })

  it("has no floating-point noise in small steps", () => {
    expect(linearTicks(0, 0.0003, 3)).toEqual([0, 0.0001, 0.0002, 0.0003])
  })

  it("answers a single value with that value", () => {
    expect(linearTicks(5, 5)).toEqual([5])
  })
})

describe("logTicks", () => {
  it("returns the powers of ten of the interval", () => {
    expect(logTicks(1e-10, 0.03)).toEqual([1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2])
  })

  it("adds 2 and 5 where there is less than two powers of ten", () => {
    expect(logTicks(0.3, 4)).toEqual([0.5, 1, 2])
  })
})

describe("linearAxis", () => {
  it("places the ends of the data at the ends of the range", () => {
    const axis = linearAxis([2, 4, 10], [0, 100])
    expect(axis.domain).toEqual([2, 10])
    expect(axis.position(2)).toBe(0)
    expect(axis.position(10)).toBe(100)
    expect(axis.position(6)).toBe(50)
  })

  it("works with a range that grows downwards, as screen coordinates do", () => {
    const axis = linearAxis([0, 1], [200, 0])
    expect(axis.position(0)).toBe(200)
    expect(axis.position(1)).toBe(0)
  })

  it("widens a domain of one value so that it can be drawn", () => {
    expect(linearAxis([3, 3], [0, 100]).domain).toEqual([2.85, 3.15])
    expect(linearAxis([0], [0, 100]).domain).toEqual([-1, 1])
    expect(linearAxis([], [0, 100]).domain).toEqual([0, 1])
  })

  it("labels ticks with the decimals their spacing needs", () => {
    const axis = linearAxis([0.093, 1], [0, 100])
    expect(axis.ticks.map(axis.format)).toEqual(["0.2", "0.4", "0.6", "0.8", "1.0"])
    const small = linearAxis([0, 0.0002156], [0, 100])
    expect(small.ticks.map(small.format)).toEqual(["0", "5e-5", "1e-4", "1.5e-4", "2e-4"])
    const steps = linearAxis([0, 16000], [0, 100])
    expect(steps.format(4000)).toBe("4000")
    const huge = linearAxis([0, 3e18], [0, 100])
    expect(huge.ticks.map(huge.format)).toEqual(["0", "1e18", "2e18", "3e18"])
  })
})

describe("logAxis", () => {
  it("places powers of ten at equal distances", () => {
    const axis = logAxis([1e-10, 1e-2], [0, 80])
    expect(axis.position(1e-10)).toBeCloseTo(0)
    expect(axis.position(1e-6)).toBeCloseTo(40)
    expect(axis.position(1e-2)).toBeCloseTo(80)
    expect(axis.format(1e-6)).toBe("1e-6")
  })

  it("ignores values that have no logarithm", () => {
    expect(logAxis([0, -1, 1e-3, 1], [0, 30]).domain).toEqual([1e-3, 1])
  })

  it("widens less than a decade to whole decades", () => {
    expect(logAxis([2, 5], [0, 10]).domain).toEqual([1, 10])
    expect(logAxis([], [0, 10]).domain).toEqual([0.1, 10])
  })
})

describe("segments", () => {
  it("breaks the line where a sample is not finite instead of bridging it", () => {
    const points: ChartPoint[] = [
      { x: 0, y: 1 },
      { x: 1, y: 2 },
      { x: 2, y: null },
      { x: 3, y: 4 },
    ]
    const runs = segments(points, (point) => point.y !== null)
    expect(runs.map((run) => run.map((point) => point.x))).toEqual([[0, 1], [3]])
  })
})

describe("paths", () => {
  it("draws one polyline per run", () => {
    const path = linePath([
      [
        { x: 0, y: 10 },
        { x: 5, y: 20 },
      ],
      [{ x: 9, y: 1 }],
    ])
    expect(path).toBe("M0.00,10.00L5.00,20.00M9.00,1.00")
  })

  it("closes the band between the extremes", () => {
    const path = bandPath([
      [
        { x: 0, low: 8, high: 2 },
        { x: 4, low: 9, high: 3 },
      ],
    ])
    expect(path).toBe("M0.00,2.00L4.00,3.00L4.00,9.00L0.00,8.00Z")
  })
})

describe("nearestIndex", () => {
  const points = [{ x: 0 }, { x: 10 }, { x: 20 }, { x: 50 }]

  it("finds the point closest to a position", () => {
    expect(nearestIndex(points, -5)).toBe(0)
    expect(nearestIndex(points, 4)).toBe(0)
    expect(nearestIndex(points, 6)).toBe(1)
    expect(nearestIndex(points, 36)).toBe(3)
    expect(nearestIndex(points, 999)).toBe(3)
    expect(nearestIndex([], 1)).toBe(-1)
  })
})
