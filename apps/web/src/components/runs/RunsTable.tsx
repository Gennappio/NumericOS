import type { ReactNode } from "react"
import { Link } from "react-router"
import type { Run } from "@/api/client"
import { StatusBadge } from "@/components/runs/StatusBadge"
import { formatSeconds } from "@/lib/format"
import { FAILURE_CLASS_LABELS, formatParameters } from "@/lib/runs"
import { formatEventTime } from "@/lib/time"

export interface RunColumn {
  title: string
  /** Right-aligned and in a fixed-width font, for numbers that are compared down a column. */
  numeric?: boolean
  cell: (run: Run) => ReactNode
}

interface RunsTableProps {
  projectId: string
  runs: Run[]
  /** Columns between the run and its timing; the default shows the parameters in one cell. */
  columns?: RunColumn[]
  caption: string
}

const PARAMETERS: RunColumn = {
  title: "Parameters",
  cell: (run) => <span className="font-mono text-xs">{formatParameters(run.parameters)}</span>,
}

/** Runs as rows. Each row says how the process stands and links to everything observed of it. */
export function RunsTable({ projectId, runs, columns = [PARAMETERS], caption }: RunsTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-border text-left text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Status
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Run
            </th>
            {columns.map((column) => (
              <th
                key={column.title}
                scope="col"
                className={`px-3 py-2 font-medium ${column.numeric ? "text-right" : ""}`}
              >
                {column.title}
              </th>
            ))}
            <th scope="col" className="px-3 py-2 font-medium">
              Started
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Duration
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              If it did not end normally
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {runs.map((run) => (
            <tr key={run.id} className="align-top">
              <td className="px-3 py-2">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-3 py-2">
                <Link
                  to={`/projects/${projectId}/runs/${run.id}`}
                  className="font-mono text-xs underline underline-offset-4"
                  title={run.id}
                >
                  {run.id.slice(0, 14)}…
                </Link>
                {run.label && <div className="text-xs text-muted-foreground">{run.label}</div>}
              </td>
              {columns.map((column) => (
                <td
                  key={column.title}
                  className={`px-3 py-2 ${column.numeric ? "text-right font-mono text-xs whitespace-nowrap" : ""}`}
                >
                  {column.cell(run)}
                </td>
              ))}
              <td className="px-3 py-2 text-xs whitespace-nowrap text-muted-foreground">
                {run.started_at ? formatEventTime(run.started_at) : "not started"}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap">
                {typeof run.wall_seconds === "number" ? formatSeconds(run.wall_seconds) : "–"}
              </td>
              <td className="max-w-md px-3 py-2 text-xs break-words">
                {run.failure_class && (
                  <span className="font-medium">{FAILURE_CLASS_LABELS[run.failure_class]}: </span>
                )}
                {run.status_reason ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
