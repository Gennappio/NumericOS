import type { EventPage } from "@/api/client"
import { POLL_MS } from "@/api/queries"
import type { Transport } from "@/api/useEventStream"
import { describeEvent } from "@/lib/events"
import { formatEventTime } from "@/lib/time"
import { cn } from "@/lib/utils"

const TRANSPORT_LABELS: Record<Transport, string> = {
  connecting: "Connecting to live updates…",
  live: "Live",
  reconnecting: `Live updates interrupted · refreshing every ${POLL_MS / 1000} s`,
}

interface EventStripProps {
  projectId: string
  /** The newest ledger entries, newest first; undefined while they are loading. */
  page: EventPage | undefined
  transport: Transport
}

/**
 * The newest entries of the project's event ledger, exactly as the backend recorded them.
 * It replays recorded events only; nothing here is inferred or reconstructed by the GUI.
 */
export function EventStrip({ projectId, page, transport }: EventStripProps) {
  return (
    <section aria-label="Recent events" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">Recent events</h2>
        <p
          role="status"
          aria-label="Live updates"
          data-transport={transport}
          className="flex items-center gap-2 text-xs text-muted-foreground"
        >
          <span
            aria-hidden="true"
            className={cn(
              "inline-block size-2 rounded-full",
              transport === "live" ? "bg-emerald-500" : "animate-pulse bg-amber-400",
            )}
          />
          {TRANSPORT_LABELS[transport]}
        </p>
      </div>

      {page === undefined ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading events…
        </p>
      ) : (
        <>
          <ol className="max-h-72 divide-y divide-border overflow-y-auto rounded-lg border border-border bg-card">
            {page.events.map((event) => (
              <li
                key={event.event_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs text-muted-foreground">#{event.seq}</span>
                <time
                  dateTime={event.timestamp_utc}
                  title={event.timestamp_utc}
                  className="text-xs text-muted-foreground"
                >
                  {formatEventTime(event.timestamp_utc)}
                </time>
                <span className="min-w-0 flex-1 basis-48 break-words">{describeEvent(event)}</span>
                <span
                  className="font-mono text-xs text-muted-foreground"
                  title={`correlation ${event.correlation_id}`}
                >
                  {event.actor}
                </span>
              </li>
            ))}
          </ol>
          <p className="text-xs text-muted-foreground">
            The {page.events.length} most recent entries of this project&apos;s event ledger,
            newest first, with their ledger position.
            {page.has_more && (
              <>
                {" "}
                Older entries: <code>numericos events list --project {projectId}</code>
              </>
            )}
          </p>
        </>
      )}
    </section>
  )
}
