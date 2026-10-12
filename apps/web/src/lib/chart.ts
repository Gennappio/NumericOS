/**
 * Geometry of the charts: axes, ticks and paths as pure functions, so that what a chart draws
 * can be checked without a browser.
 */

export interface ChartPoint {
  x: number
  /** Null where the sample is not finite: the line breaks there, it is never bridged. */
  y: number | null
  /** Extremes of the samples this point stands for, when it stands for more than one. */
  low?: number | null
  high?: number | null
}

export interface Axis {
  domain: [number, number]
  ticks: number[]
  position(value: number): number
  format(value: number): string
}

function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count)
  const power = 10 ** Math.floor(Math.log10(raw))
  const fraction = raw / power
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * power
}

/** Round, evenly spaced values inside [min, max]. */
export function linearTicks(min: number, max: number, count = 5): number[] {
  if (min === max) return [min]
  const step = niceStep(max - min, count)
  const ticks: number[] = []
  for (let index = Math.ceil(min / step); index * step <= max + step * 1e-9; index += 1) {
    ticks.push(Number((index * step).toPrecision(12)))
  }
  return ticks
}

/** Powers of ten inside [min, max]; with fewer than two of them, 2 and 5 times each as well. */
export function logTicks(min: number, max: number): number[] {
  const first = Math.floor(Math.log10(min))
  const last = Math.ceil(Math.log10(max))
  const decades: number[] = []
  // Parsed, not computed: 10 ** -7 is not exactly 1e-7 in floating point.
  for (let exponent = first; exponent <= last; exponent += 1) decades.push(Number(`1e${exponent}`))
  const inside = (value: number) => value >= min * (1 - 1e-9) && value <= max * (1 + 1e-9)
  const powers = decades.filter(inside)
  if (powers.length >= 2) return powers
  return decades
    .flatMap((decade) => [decade, 2 * decade, 5 * decade])
    .filter(inside)
    .map((value) => Number(value.toPrecision(12)))
}

/** One notation for all the ticks of an axis: decimals where they read well, else exponents. */
function tickFormat(step: number, largest: number): (value: number) => string {
  if (step < 1e-3 || largest >= 1e6) {
    return (value) =>
      value === 0 ? "0" : Number(value.toPrecision(6)).toExponential().replace("e+", "e")
  }
  const decimals = Math.max(0, -Math.floor(Math.log10(step) + 1e-9))
  return (value) => value.toFixed(decimals)
}

/** A domain around the values; one that is a single value is widened so that it can be drawn. */
function extent(values: number[]): [number, number] {
  let min = Infinity
  let max = -Infinity
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
  }
  if (min === Infinity) return [0, 1]
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.05
    return [min - pad, max + pad]
  }
  return [min, max]
}

export function linearAxis(values: number[], range: [number, number], count = 5): Axis {
  const domain = extent(values)
  const ticks = linearTicks(domain[0], domain[1], count)
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : Math.abs(domain[1] - domain[0]) || 1
  const scale = (range[1] - range[0]) / (domain[1] - domain[0])
  return {
    domain,
    ticks,
    position: (value) => range[0] + (value - domain[0]) * scale,
    format: tickFormat(step, Math.max(Math.abs(domain[0]), Math.abs(domain[1]))),
  }
}

/** A logarithmic axis. Only positive values can be placed on it: callers leave the rest out. */
export function logAxis(values: number[], range: [number, number]): Axis {
  const positive = values.filter((value) => value > 0)
  let [min, max] = extent(positive)
  if (min <= 0 || positive.length === 0) [min, max] = [0.1, 10]
  if (max / min < 10) {
    // Less than a decade: widen to whole decades so that the axis has labels to read.
    min = 10 ** Math.floor(Math.log10(min))
    max = 10 ** Math.ceil(Math.log10(max) + 1e-12)
    if (min === max) max = min * 10
  }
  const low = Math.log10(min)
  const scale = (range[1] - range[0]) / (Math.log10(max) - low)
  return {
    domain: [min, max],
    ticks: logTicks(min, max),
    position: (value) => range[0] + (Math.log10(value) - low) * scale,
    format: (value) => Number(value.toPrecision(3)).toExponential().replace("e+", "e"),
  }
}

/** Runs of consecutive points that can be drawn; a point that cannot ends the current run. */
export function segments<T extends ChartPoint>(points: T[], drawable: (point: T) => boolean): T[][] {
  const runs: T[][] = []
  let current: T[] = []
  for (const point of points) {
    if (drawable(point)) {
      current.push(point)
    } else if (current.length > 0) {
      runs.push(current)
      current = []
    }
  }
  if (current.length > 0) runs.push(current)
  return runs
}

const pair = (x: number, y: number) => `${x.toFixed(2)},${y.toFixed(2)}`

/** SVG path of one polyline per run of points. */
export function linePath(runs: { x: number; y: number }[][]): string {
  return runs
    .map((run) => run.map((point, index) => `${index === 0 ? "M" : "L"}${pair(point.x, point.y)}`).join(""))
    .join("")
}

/** SVG path of the area between an upper and a lower edge, one closed shape per run. */
export function bandPath(runs: { x: number; low: number; high: number }[][]): string {
  return runs
    .map((run) => {
      const upper = run.map((point, index) => `${index === 0 ? "M" : "L"}${pair(point.x, point.high)}`)
      const lower = [...run].reverse().map((point) => `L${pair(point.x, point.low)}`)
      return `${upper.join("")}${lower.join("")}Z`
    })
    .join("")
}

/** Index of the point whose x is nearest to `x`; points are ordered by x. */
export function nearestIndex(points: { x: number }[], x: number): number {
  if (points.length === 0) return -1
  let low = 0
  let high = points.length - 1
  while (high - low > 1) {
    const middle = (low + high) >> 1
    if (points[middle].x <= x) low = middle
    else high = middle
  }
  return Math.abs(points[low].x - x) <= Math.abs(points[high].x - x) ? low : high
}
