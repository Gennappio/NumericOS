import type { EventOut } from "@/api/client"
import { describeEvent } from "@/lib/events"
import { formatEventTime } from "@/lib/time"
import { cn } from "@/lib/utils"

const SEVERITY_STYLES: Record<string, string> = {
  error: "bg-red-600",
  warning: "bg-amber-500",
  info: "bg-slate-400",
  debug: "bg-slate-300",
}

/**
 * What happened to a run, in the order the ledger recorded it. The time shown is when each
 * event was recorded; the moments the events are about are in the run's own fields.
 */
export function RunEvents({ events }: { events: EventOut[] }) {
  return (
    <ol className="divide-y divide-border rounded-lg border border-border bg-card">
      {events.map((event) => (
        <li
          key={event.event_id}
          data-severity={event.severity}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2 text-sm"
        >
          <span
            aria-hidden="true"
            className={cn(
              "inline-block size-2 shrink-0 self-center rounded-full",
              SEVERITY_STYLES[event.severity] ?? SEVERITY_STYLES.info,
            )}
          />
          <span className="font-mono text-xs text-muted-foreground">#{event.seq}</span>
          <time dateTime={event.timestamp_utc} className="text-xs text-muted-foreground">
            {formatEventTime(event.timestamp_utc)}
          </time>
          <span className="min-w-0 flex-1 basis-64 break-words">
            {event.severity === "error" || event.severity === "warning" ? (
              <span className="sr-only">{event.severity}: </span>
            ) : null}
            {describeEvent(event)}
          </span>
          <span className="font-mono text-xs text-muted-foreground">{event.actor}</span>
        </li>
      ))}
    </ol>
  )
}
