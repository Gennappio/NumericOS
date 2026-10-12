import { useId, useState, type FormEvent } from "react"
import { Link, useNavigate, useParams } from "react-router"
import type { Run } from "@/api/client"
import {
  isActive,
  RUN_POLL_MS,
  useArtifacts,
  useCancelRun,
  useExperiment,
  useRerun,
  useRun,
  useRunEvents,
  useRunMetrics,
  useWorkers,
} from "@/api/queries"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
import { ArtifactsPanel } from "@/components/runs/ArtifactsPanel"
import { CoveragePanel } from "@/components/runs/CoveragePanel"
import { MetricsPanel } from "@/components/runs/MetricsPanel"
import { OutputPanel } from "@/components/runs/OutputPanel"
import { ProvenancePanel } from "@/components/runs/ProvenancePanel"
import { ResourcesPanel } from "@/components/runs/ResourcesPanel"
import { RunEvents } from "@/components/runs/RunEvents"
import { StatusBadge } from "@/components/runs/StatusBadge"
import { Section } from "@/components/Section"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { describeError } from "@/lib/errors"
import { formatSeconds } from "@/lib/format"
import { FAILURE_CLASS_LABELS, formatParameters, RUN_STATUS_HINTS } from "@/lib/runs"
import { formatEventTime } from "@/lib/time"
import { useProjectContext } from "@/pages/projectContext"

export function RunView() {
  const { runId = "" } = useParams()
  // Keyed by run: another run starts with clean feeds and charts.
  return <RunMonitor key={runId} runId={runId} />
}

/**
 * Everything observed of one run, while it runs and afterwards: how its process stands, how
 * far the observation reaches, its metrics, its resources, its output, exactly what ran, what
 * happened to it and the files it left.
 */
function RunMonitor({ runId }: { runId: string }) {
  const { project, offline } = useProjectContext()
  const run = useRun(project.id, runId)
  const active = isActive(run.data?.status)
  const metrics = useRunMetrics(project.id, runId, active)
  const events = useRunEvents(project.id, runId)
  const artifacts = useArtifacts(project.id, runId)
  const experiment = useExperiment(project.id, run.data?.experiment_id ?? "")
  const workers = useWorkers()
  const [notice, setNotice] = useState<string | null>(null)

  if (run.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading run…
      </p>
    )
  }
  if (run.isError) {
    return (
      <ErrorPanel title="Could not load the run" error={run.error} onRetry={() => void run.refetch()} />
    )
  }

  const data = run.data
  const waiting = data.status === "queued" && workers.data !== undefined && workers.data.alive === 0
  return (
    <div className="space-y-8">
      <RunHeader
        run={data}
        projectId={project.id}
        experimentName={experiment.data?.name}
        offline={offline}
        onError={setNotice}
      />
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      {waiting && (
        <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          No supervisor is running, so this run stays queued. Start one with{" "}
          <code className="font-mono text-xs">make worker</code>.
        </p>
      )}

      <Section
        title="How far the observation reaches"
        description="Each level says whether it has data. None of them says that the result is valid."
        aside={
          active ? (
            <p role="status" className="text-xs text-muted-foreground">
              Re-read every {RUN_POLL_MS / 1000} s while the run goes on
            </p>
          ) : undefined
        }
      >
        {metrics.data ? (
          <CoveragePanel metrics={metrics.data} />
        ) : metrics.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading coverage…
          </p>
        ) : (
          <ErrorPanel
            title="Could not load the metrics"
            error={metrics.error}
            onRetry={() => void metrics.refetch()}
          />
        )}
      </Section>

      <Section
        title="Metrics"
        description="Numbers the program emitted, a parser read from its output, or the supervisor measured. The band behind a line is the range of the samples each point stands for."
      >
        {metrics.data && (
          <MetricsPanel
            projectId={project.id}
            runId={runId}
            metrics={metrics.data}
            protocol={experiment.data?.protocol}
            active={active}
          />
        )}
      </Section>

      <Section title="Process resources">
        <ResourcesPanel run={data} />
      </Section>

      <Section title="Output">
        <OutputPanel run={data} />
      </Section>

      <Section title="What ran">
        <ProvenancePanel run={data} />
      </Section>

      <Section title="What happened">
        {events.data ? (
          <RunEvents events={events.data.events} />
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            Loading events…
          </p>
        )}
      </Section>

      <Section title="Files">
        <ArtifactsPanel artifacts={artifacts.data?.artifacts ?? []} ended={!active} />
      </Section>
    </div>
  )
}

function RunHeader({
  run,
  projectId,
  experimentName,
  offline,
  onError,
}: {
  run: Run
  projectId: string
  experimentName: string | undefined
  offline: boolean
  onError: (message: string) => void
}) {
  const navigate = useNavigate()
  const rerun = useRerun(projectId, run.id)
  const [cancelling, setCancelling] = useState(false)
  const [key] = useState(() => crypto.randomUUID())
  const active = isActive(run.status)
  const exact = run.code?.mode === "ref"
  const abnormal = run.status !== "succeeded" && !active

  return (
    <header className="space-y-3">
      <p className="text-sm">
        <Link to={`/projects/${projectId}/experiments`} className="underline underline-offset-4">
          Experiments
        </Link>{" "}
        <span className="text-muted-foreground">/ </span>
        <Link
          to={`/projects/${projectId}/experiments/${run.experiment_id}`}
          className="underline underline-offset-4"
        >
          {experimentName ?? "experiment"}
        </Link>{" "}
        <span className="text-muted-foreground">/ run</span>
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="font-mono text-base font-semibold break-all">{run.id}</h2>
          <StatusBadge status={run.status} />
          {run.label && <span className="text-sm text-muted-foreground">{run.label}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {active && (
            <Button variant="destructive" onClick={() => setCancelling(true)} disabled={offline || Boolean(run.cancel_requested_at)}>
              {run.cancel_requested_at ? "Stop requested" : "Stop the run…"}
            </Button>
          )}
          {!active && exact && (
            <Button
              variant="outline"
              disabled={offline || rerun.isPending}
              title="Queue a run with the same commit, parameters and seed"
              onClick={() =>
                rerun.mutate(key, {
                  onSuccess: (again) => navigate(`/projects/${projectId}/runs/${again.id}`),
                  onError: (error) => onError(describeError(error)),
                })
              }
            >
              Run again
            </Button>
          )}
        </div>
      </div>

      <p className="font-mono text-xs break-words">{formatParameters(run.parameters)}</p>
      <p className="text-sm text-muted-foreground">
        {/* A normal end has its own note below; saying it twice would bury it. */}
        {run.status !== "succeeded" && `${RUN_STATUS_HINTS[run.status]} `}
        {run.started_at && `Started ${formatEventTime(run.started_at)}. `}
        {run.finished_at && `Ended ${formatEventTime(run.finished_at)}`}
        {typeof run.wall_seconds === "number" && ` after ${formatSeconds(run.wall_seconds)}`}
        {run.finished_at && ". "}
        {typeof run.exit_code === "number" && `Exit code ${run.exit_code}. `}
        {run.exit_signal && `Ended by ${run.exit_signal}. `}
      </p>

      {abnormal && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-950"
        >
          <span className="font-medium">
            {run.failure_class ? FAILURE_CLASS_LABELS[run.failure_class] : "Not a normal end"}
          </span>
          {run.status_reason && <>: {run.status_reason}</>}
          <p className="mt-1 text-xs">
            What was observed until then is kept below: this run is evidence, not waste.
          </p>
        </div>
      )}
      {run.status === "succeeded" && (
        <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
          The process ended normally. That is a statement about the process: no validator has
          judged the result.
        </p>
      )}

      <Dialog open={cancelling} onOpenChange={setCancelling}>
        <DialogContent className="sm:max-w-md">
          <CancelForm projectId={projectId} runId={run.id} onDone={() => setCancelling(false)} />
        </DialogContent>
      </Dialog>
    </header>
  )
}

function CancelForm({
  projectId,
  runId,
  onDone,
}: {
  projectId: string
  runId: string
  onDone: () => void
}) {
  const id = useId()
  const cancel = useCancelRun(projectId, runId)
  const [reason, setReason] = useState("")
  const [error, setError] = useState<unknown>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    cancel.mutate(reason.trim(), { onSuccess: onDone, onError: setError })
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Stop the run</DialogTitle>
        <DialogDescription>
          The program and every process it started get SIGTERM, then SIGKILL after the grace
          period of the contract. What was observed so far is kept.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-reason`} className="text-sm font-medium">
          Why (recorded with the run)
        </label>
        <Input
          id={`${id}-reason`}
          value={reason}
          maxLength={300}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Keep it running</DialogClose>
        <Button type="submit" variant="destructive" disabled={cancel.isPending}>
          Stop the run
        </Button>
      </DialogFooter>
    </form>
  )
}
