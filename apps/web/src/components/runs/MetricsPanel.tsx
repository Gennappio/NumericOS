import type { ExperimentProtocol, RunMetrics } from "@/api/client"
import { MetricChart } from "@/components/runs/MetricChart"
import { formatBytes, formatValue } from "@/lib/format"

interface MetricsPanelProps {
  projectId: string
  runId: string
  metrics: RunMetrics
  protocol: ExperimentProtocol | undefined
  active: boolean
}

/**
 * The numbers of a run that have a scientific meaning: a chart for every series that has more
 * than one sample, a table for the quantities measured once.
 */
export function MetricsPanel({ projectId, runId, metrics, protocol, active }: MetricsPanelProps) {
  const curves = metrics.series.filter((series) => series.samples > 1)
  const scalars = metrics.series.filter((series) => series.samples === 1)

  if (metrics.series.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {active
          ? "No metric has a sample yet."
          : "No metric was recorded: nothing numerical is known about this run beyond its process."}
      </p>
    )
  }
  return (
    <div className="space-y-4">
      {curves.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-2">
          {curves.map((series) => (
            <MetricChart
              key={series.name}
              projectId={projectId}
              runId={runId}
              series={series}
              protocol={protocol}
              active={active}
            />
          ))}
        </div>
      )}
      {scalars.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <caption className="sr-only">Quantities measured once</caption>
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Measured once</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                <th scope="col" className="px-3 py-2 font-medium">Unit</th>
                <th scope="col" className="px-3 py-2 font-medium">Measured by</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {scalars.map((series) => (
                <tr key={series.name}>
                  <td className="px-3 py-2 font-mono text-xs">
                    {series.name}
                    {!series.declared && (
                      <span className="font-sans text-muted-foreground"> (not declared)</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatValue(series.last_value, series.last_non_finite, 10)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {series.unit || "–"}
                    {series.unit === "bytes" && typeof series.last_value === "number" && (
                      <span className="font-sans text-muted-foreground">
                        {" "}
                        ({formatBytes(series.last_value)})
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">{series.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
