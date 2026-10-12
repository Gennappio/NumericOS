import { useCallback, useEffect, useRef, useState } from "react"
import { api, type CursorStart, type LogLine, type Run } from "@/api/client"
import { useCursorFeed } from "@/api/useCursorFeed"
import { describeError } from "@/lib/errors"
import { cn } from "@/lib/utils"

type Stream = LogLine["stream"]

const STREAMS: { name: Stream; label: string }[] = [
  { name: "stdout", label: "Standard output" },
  { name: "stderr", label: "Standard error" },
  { name: "build", label: "Build" },
]
const STREAM_STYLES: Record<Stream, string> = {
  stdout: "text-slate-500",
  stderr: "text-red-700",
  build: "text-violet-700",
}
const TAIL = 300
const KEPT = 3000

function clock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString().slice(11, 23)
}

/**
 * What the program printed. It is closed until asked for: a wall of log lines is not the first
 * thing to read about a run. Open, it shows the last lines with the time each one arrived and
 * follows the run.
 */
export function OutputPanel({ run }: { run: Run }) {
  const [open, setOpen] = useState(false)
  const records = run.outcome?.output.records ?? 0
  return (
    <details
      className="rounded-lg border border-border bg-card"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        Show the program&apos;s output
        {run.outcome && (
          <span className="font-normal text-muted-foreground">
            {" "}
            · {run.outcome.output.stdout_lines} lines on standard output,{" "}
            {run.outcome.output.stderr_lines} on standard error
            {run.outcome.output.build_lines > 0 && `, ${run.outcome.output.build_lines} from the build`}
          </span>
        )}
      </summary>
      {open && <OutputFeed runId={run.id} records={records} truncated={run.outcome?.output.truncated ?? false} />}
    </details>
  )
}

function OutputFeed({
  runId,
  records,
  truncated,
}: {
  runId: string
  records: number
  truncated: boolean
}) {
  const read = useCallback(
    async (start: CursorStart) => {
      const page = await api.readLogs(runId, start, 1000)
      return { ...page, items: page.lines }
    },
    [runId],
  )
  const feed = useCursorFeed<LogLine>(read, { tail: TAIL, keep: KEPT, intervalMs: 1000 })
  const [hidden, setHidden] = useState<Stream[]>([])
  const [follow, setFollow] = useState(true)
  const box = useRef<HTMLDivElement>(null)
  const lines = feed.items.filter((line) => !hidden.includes(line.stream))

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [follow, lines.length])

  return (
    <div className="space-y-2 border-t border-border p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {STREAMS.map((stream) => (
          <label key={stream.name} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={!hidden.includes(stream.name)}
              onChange={(event) =>
                setHidden(
                  event.target.checked
                    ? hidden.filter((name) => name !== stream.name)
                    : [...hidden, stream.name],
                )
              }
            />
            {stream.label}
          </label>
        ))}
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={follow}
            onChange={(event) => setFollow(event.target.checked)}
          />
          Follow new lines
        </label>
        <span className="text-muted-foreground">
          {feed.complete ? "Complete" : "Following the run"}
        </span>
      </div>

      {feed.error !== undefined ? (
        <p role="alert" className="text-sm text-muted-foreground">
          {describeError(feed.error)}
        </p>
      ) : (
        <div
          ref={box}
          role="log"
          aria-label="Program output"
          className="max-h-96 overflow-auto rounded-md bg-slate-950 p-2 font-mono text-xs leading-5 text-slate-100"
        >
          {lines.length === 0 ? (
            <p className="text-slate-400">{feed.loading ? "Loading…" : "No output recorded."}</p>
          ) : (
            lines.map((line, index) => (
              <div key={`${line.t}-${index}`} className="flex gap-2 whitespace-pre-wrap">
                <span className="shrink-0 text-slate-500 select-none">{clock(line.t)}</span>
                <span className={cn("w-7 shrink-0 select-none", STREAM_STYLES[line.stream])}>
                  {line.stream === "stdout" ? "out" : line.stream === "stderr" ? "err" : "bld"}
                </span>
                <span className="min-w-0 break-all">
                  {line.text}
                  {line.cut && <span className="text-amber-400"> [line cut at 1 MiB]</span>}
                </span>
              </div>
            ))
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        The last {TAIL} lines when this was opened, and what arrived since; times are UTC.
        {feed.dropped > 0 && ` ${feed.dropped} older lines were let go here.`}
        {records > 0 &&
          ` ${records} lines were metric or event records: they are shown as metrics and events, not here.`}
        {truncated && " Output beyond the limit of the contract was not stored."} Everything is in
        the file <span className="font-mono">output.jsonl</span> of the run, or with{" "}
        <code className="font-mono">numericos run logs {runId}</code>.
      </p>
    </div>
  )
}
