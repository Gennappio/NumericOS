import type { RunMetrics } from "@/api/client"
import { COVERAGE_LABELS, COVERAGE_STYLES } from "@/lib/runs"
import { cn } from "@/lib/utils"

type Status = keyof typeof COVERAGE_LABELS

function Chip({ status }: { status: Status }) {
  return (
    <span
      data-coverage={status}
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded-full border px-2 text-xs font-medium whitespace-nowrap",
        COVERAGE_STYLES[status],
      )}
    >
      {COVERAGE_LABELS[status]}
    </span>
  )
}

/**
 * How far the observation of a run reaches, level by level, and what is missing. It lists
 * unknowns as prominently as what is known, and it never says that a result is valid.
 */
export function CoveragePanel({ metrics }: { metrics: RunMetrics }) {
  const { coverage } = metrics
  const unobserved = coverage.metrics.filter((metric) => metric.status !== "observed")
  return (
    <div className="space-y-3">
      <ul className="divide-y divide-border rounded-lg border border-border bg-card">
        {coverage.levels.map((level) => (
          <li
            key={level.level}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-sm"
          >
            <span className="w-7 font-mono text-xs text-muted-foreground">{level.level}</span>
            <span className="w-36 font-medium">{level.title}</span>
            <Chip status={level.status} />
            <span className="min-w-0 flex-1 basis-64 text-muted-foreground">{level.detail}</span>
          </li>
        ))}
      </ul>

      {unobserved.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-3 text-sm">
          <p className="font-medium">Declared by the contract, without a sample</p>
          <ul className="mt-1 space-y-1">
            {unobserved.map((metric) => (
              <li key={metric.name} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{metric.name}</span>
                <span className="text-xs text-muted-foreground">measured by the {metric.source}</span>
                <Chip status={metric.status} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {coverage.undeclared.length > 0 && (
        <p className="text-sm text-muted-foreground">
          Emitted by the program without being declared in the contract:{" "}
          <span className="font-mono text-xs text-foreground">{coverage.undeclared.join(", ")}</span>
        </p>
      )}
      {metrics.truncated && (
        <p className="text-sm text-amber-800">
          Samples beyond the storage limit of the contract were counted, not stored.
        </p>
      )}

      {metrics.diagnostics.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          <p className="font-medium">Problems with what the program reported</p>
          <ul className="mt-1 space-y-2">
            {metrics.diagnostics.map((item) => (
              <li key={item.kind}>
                {item.message} <span className="text-xs">({item.count}×)</span>
                <ul className="mt-0.5 font-mono text-xs break-all">
                  {item.examples.map((example) => (
                    <li key={example}>{example}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
