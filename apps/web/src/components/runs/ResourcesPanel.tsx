import { useCallback } from "react"
import { api, type CursorStart, type ResourceSample, type Run } from "@/api/client"
import { isActive } from "@/api/queries"
import { useCursorFeed } from "@/api/useCursorFeed"
import { LineChart } from "@/components/charts/LineChart"
import { describeError } from "@/lib/errors"
import { formatBytes, formatSeconds } from "@/lib/format"

const MIB = 1024 * 1024
/** More points than a chart is wide add nothing: longer records are thinned for drawing. */
const DRAWN = 600

function thin<T>(items: T[]): T[] {
  if (items.length <= DRAWN) return items
  const stride = Math.ceil(items.length / DRAWN)
  return items.filter((_, index) => index % stride === 0 || index === items.length - 1)
}

/**
 * What the process of a run used. Two sources, labelled as what they are: totals from the
 * operating system when the program ended, which are exact, and samples of the process tree
 * taken at an interval, which show the course and can miss a peak between two of them.
 */
export function ResourcesPanel({ run }: { run: Run }) {
  const read = useCallback(
    async (start: CursorStart) => {
      const page = await api.readResources(run.id, start, 2000)
      return { ...page, items: page.samples }
    },
    [run.id],
  )
  const feed = useCursorFeed<ResourceSample>(read, { keep: 20000, intervalMs: 1000 })
  const usage = run.outcome?.rusage
  const samples = thin(feed.items)

  return (
    <div className="space-y-3">
      <dl className="grid gap-3 rounded-lg border border-border bg-card p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Fact
          term="Program wall time"
          value={
            typeof run.outcome?.program_seconds === "number"
              ? formatSeconds(run.outcome.program_seconds)
              : "–"
          }
          note={
            typeof run.outcome?.program_seconds === "number"
              ? "from its start to its exit"
              : "known when the program has ended"
          }
        />
        <Fact
          term="CPU time"
          value={
            usage ? formatSeconds(usage.cpu_user_seconds + usage.cpu_system_seconds) : "–"
          }
          note={
            usage
              ? `${formatSeconds(usage.cpu_user_seconds)} user, ${formatSeconds(usage.cpu_system_seconds)} system`
              : "known when the program has ended"
          }
        />
        <Fact
          term="Largest process"
          value={usage ? formatBytes(usage.max_rss_bytes) : "–"}
          note="resident memory, from the system at exit"
        />
        <Fact
          term="Sampled maximum"
          value={run.resources?.samples ? formatBytes(run.resources.max_rss_bytes ?? 0) : "–"}
          note={
            run.resources?.samples
              ? `over the process tree, in ${run.resources.samples} samples`
              : "no sample was taken"
          }
        />
      </dl>

      {feed.error !== undefined ? (
        <p role="alert" className="text-sm text-muted-foreground">
          {describeError(feed.error)}
        </p>
      ) : samples.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {feed.loading || (!feed.complete && !isActive(run.status))
            ? "Reading the samples…"
            : feed.complete
              ? "No resource sample exists: the program ended before the first one was due. The totals above are exact."
              : "No resource sample yet."}
        </p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="min-w-0 rounded-lg border border-border bg-card p-3">
            <h4 className="text-sm font-medium">CPU use of the process tree, % of one core</h4>
            <LineChart
              label="CPU use over elapsed seconds"
              xLabel="seconds"
              baseline={0}
              points={samples.map((sample) => ({ x: sample.elapsed, y: sample.cpu_percent }))}
            />
          </div>
          <div className="min-w-0 rounded-lg border border-border bg-card p-3">
            <h4 className="text-sm font-medium">Resident memory of the process tree, MiB</h4>
            <LineChart
              label="Resident memory over elapsed seconds"
              xLabel="seconds"
              baseline={0}
              points={samples.map((sample) => ({ x: sample.elapsed, y: sample.rss_bytes / MIB }))}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function Fact({ term, value, note }: { term: string; value: string; note: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted-foreground uppercase">{term}</dt>
      <dd className="font-mono text-base">{value}</dd>
      <dd className="text-xs text-muted-foreground">{note}</dd>
    </div>
  )
}
