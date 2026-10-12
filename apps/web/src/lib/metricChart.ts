import type { MetricOverview } from "@/api/client"
import type { ChartPoint } from "@/lib/chart"

/** A position on a chart where a sample is not finite and so cannot be drawn. */
export interface Mark {
  x: number
  label: string
}

/**
 * Chart coordinates of a series. Samples are placed at their step when every stretch has one
 * and the steps only increase; otherwise by their position in the series. Each point is the
 * last sample of its stretch, with the extremes of the stretch around it.
 */
export function chartData(overview: MetricOverview): {
  points: ChartPoint[]
  marks: Mark[]
  xLabel: "step" | "sample"
} {
  const steps = overview.buckets.map((bucket) => bucket.last_step)
  const byStep = steps.every(
    (step, index) =>
      typeof step === "number" && (index === 0 || step > (steps[index - 1] as number)),
  )
  const xLabel = byStep ? "step" : "sample"
  const points: ChartPoint[] = []
  const marks: Mark[] = []
  let seen = 0
  for (const bucket of overview.buckets) {
    seen += bucket.samples
    const x = byStep ? (bucket.last_step as number) : seen
    const many = bucket.samples > 1
    points.push({
      x,
      y: bucket.last_value ?? null,
      low: many ? bucket.min_value : undefined,
      high: many ? bucket.max_value : undefined,
    })
    if (bucket.non_finite > 0) {
      const count = bucket.non_finite === 1 ? "a sample" : `${bucket.non_finite} samples`
      marks.push({ x, label: `${count} not finite at ${xLabel} ${x}` })
    }
  }
  return { points, marks, xLabel }
}
