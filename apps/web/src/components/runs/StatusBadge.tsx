import type { RunStatus } from "@/api/client"
import { RUN_STATUS_HINTS, RUN_STATUS_LABELS, RUN_STATUS_STYLES } from "@/lib/runs"
import { cn } from "@/lib/utils"

/**
 * How the process of a run stands or ended. It is worded and coloured as an operational fact:
 * a run that ended normally is not shown as a success of its science.
 */
export function StatusBadge({ status }: { status: RunStatus }) {
  const moving = status === "running" || status === "starting"
  return (
    <span
      title={RUN_STATUS_HINTS[status]}
      data-status={status}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        RUN_STATUS_STYLES[status],
      )}
    >
      {moving && (
        <span aria-hidden="true" className="inline-block size-1.5 animate-pulse rounded-full bg-current" />
      )}
      {RUN_STATUS_LABELS[status]}
    </span>
  )
}
