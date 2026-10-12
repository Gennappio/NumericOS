import { useState } from "react"
import type { ExperimentProtocol, SeriesSummary } from "@/api/client"
import { useMetricOverview } from "@/api/queries"
import { LineChart, type Threshold } from "@/components/charts/LineChart"
import { Button } from "@/components/ui/button"
import { describeError } from "@/lib/errors"
import { formatNumber, formatValue } from "@/lib/format"
import { chartData } from "@/lib/metricChart"
import { ruleBound, rulesFor } from "@/lib/protocol"

interface MetricChartProps {
  projectId: string
  runId: string
  series: SeriesSummary
  /** The contract of the run, for the bounds it states on this metric. */
  protocol: ExperimentProtocol | undefined
  active: boolean
}

/** One metric of a run over its steps, re-read while the run goes on. */
export function MetricChart({ projectId, runId, series, protocol, active }: MetricChartProps) {
  const overview = useMetricOverview(projectId, runId, series.name, active)
  const positive = typeof series.min_value === "number" && series.min_value > 0
  const wide = positive && (series.max_value ?? 0) / (series.min_value as number) >= 1000
  const [chosen, setChosen] = useState<"linear" | "log" | null>(null)
  const scale = chosen ?? (wide ? "log" : "linear")

  const thresholds: Threshold[] = protocol
    ? rulesFor(protocol, series.name).flatMap((rule) => {
        const bound = ruleBound(rule)
        if (!bound) return []
        const consequence = (rule.action ?? "halt") === "halt" ? "stops the run" : "is recorded"
        return [{ value: bound.value, label: `${bound.side} ${formatNumber(bound.value)} ${consequence}` }]
      })
    : []

  return (
    <article
      aria-label={`Metric ${series.name}`}
      className="min-w-0 space-y-2 rounded-lg border border-border bg-card p-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="font-mono text-sm font-medium">
          {series.name}
          {series.unit && <span className="font-normal text-muted-foreground"> [{series.unit}]</span>}
        </h4>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {series.source}
            {!series.declared && " · not declared"}
          </span>
          <Button
            variant={scale === "log" ? "default" : "outline"}
            size="xs"
            aria-pressed={scale === "log"}
            title="Draw the vertical axis logarithmically"
            onClick={() => setChosen(scale === "log" ? "linear" : "log")}
          >
            Log axis
          </Button>
        </div>
      </header>
      <p className="text-xs text-muted-foreground">
        {series.samples} samples · last{" "}
        <span className="font-mono text-foreground">
          {formatValue(series.last_value, series.last_non_finite, 8)}
        </span>
        {typeof series.last_step === "number" && ` at step ${series.last_step}`}
        {typeof series.min_value === "number" && typeof series.max_value === "number" && (
          <>
            {" "}
            · range{" "}
            <span className="font-mono">
              {formatNumber(series.min_value)} .. {formatNumber(series.max_value)}
            </span>
          </>
        )}
        {series.non_finite > 0 && (
          <span className="font-medium text-red-700"> · {series.non_finite} not finite</span>
        )}
        {series.stored < series.samples && ` · only ${series.stored} stored`}
      </p>
      {overview.data ? (
        <LineChart
          label={`${series.name} over ${chartData(overview.data).xLabel}`}
          {...chartData(overview.data)}
          scale={scale}
          thresholds={thresholds}
        />
      ) : overview.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading samples…
        </p>
      ) : (
        <p role="alert" className="text-sm text-muted-foreground">
          {describeError(overview.error)}
        </p>
      )}
    </article>
  )
}
