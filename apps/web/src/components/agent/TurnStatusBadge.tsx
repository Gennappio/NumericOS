import type { MessageStatus } from "@/api/client"
import { TURN_STATUS_HINTS, TURN_STATUS_LABELS, TURN_STATUS_STYLES } from "@/lib/agent"
import { cn } from "@/lib/utils"

/** How a turn of the agent stands or ended, as an operational fact. */
export function TurnStatusBadge({ status }: { status: MessageStatus }) {
  return (
    <span
      title={TURN_STATUS_HINTS[status]}
      data-status={status}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        TURN_STATUS_STYLES[status],
      )}
    >
      {status === "running" && (
        <span aria-hidden="true" className="inline-block size-1.5 animate-pulse rounded-full bg-current" />
      )}
      {TURN_STATUS_LABELS[status]}
    </span>
  )
}
