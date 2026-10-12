import { useId, useState, type FormEvent } from "react"
import type { Project } from "@/api/client"
import { useTrustExecution, useWorkers } from "@/api/queries"
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
import { describeError } from "@/lib/errors"
import { formatTimestamp } from "@/lib/time"

interface ExecutionPanelProps {
  project: Project
  disabled: boolean
  /** What the permission is asked for: it changes the wording, not the permission. */
  purpose?: "experiments" | "agent"
}

/**
 * The two preconditions of running anything: the project directory was explicitly trusted,
 * and a supervisor process is alive to execute queued runs. Both are shown as they are.
 */
export function ExecutionPanel({ project, disabled, purpose = "experiments" }: ExecutionPanelProps) {
  const workers = useWorkers()
  const [asking, setAsking] = useState(false)
  const trusted = Boolean(project.execution_trusted_at)
  const alive = workers.data?.alive ?? 0
  const busy = workers.data?.workers.filter((worker) => worker.alive) ?? []
  const forAgent = purpose === "agent"

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div
        data-state={trusted ? "trusted" : "untrusted"}
        className="space-y-2 rounded-lg border border-border bg-card p-4"
      >
        <h3 className="text-sm font-medium">Code execution</h3>
        {project.root_path === null ? (
          <p className="text-sm text-muted-foreground">
            This project has no code path. Set the path of its Git repository with{" "}
            <span className="font-medium text-foreground">Edit project</span>{" "}
            {forAgent ? "to talk to the agent about its code." : "to run experiments."}
          </p>
        ) : trusted ? (
          <p className="text-sm">
            Allowed in <span className="font-mono text-xs break-all">{project.root_path}</span>{" "}
            <span className="text-muted-foreground">
              since {formatTimestamp(project.execution_trusted_at!)}
            </span>
          </p>
        ) : (
          <>
            <p className="text-sm">
              Not allowed yet.{" "}
              {forAgent
                ? "The agent reads, edits and runs the code of this project with your permissions, in"
                : "Running an experiment executes the code of this project with your permissions, in"}{" "}
              <span className="font-mono text-xs break-all">{project.root_path}</span>
            </p>
            <Button onClick={() => setAsking(true)} disabled={disabled}>
              Allow execution in this directory…
            </Button>
          </>
        )}
      </div>

      <div
        data-state={alive > 0 ? "alive" : "absent"}
        className="space-y-2 rounded-lg border border-border bg-card p-4"
      >
        <h3 className="text-sm font-medium">Supervisor</h3>
        {workers.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            Checking…
          </p>
        ) : workers.isError ? (
          <p className="text-sm text-muted-foreground">{describeError(workers.error)}</p>
        ) : alive > 0 ? (
          <ul className="space-y-1 text-sm">
            {busy.map((worker) => (
              <li key={worker.id}>
                Running: process {worker.pid} on {worker.hostname},{" "}
                {worker.active_runs} of {worker.max_parallel_runs} runs in progress
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm">
            <span className="font-medium text-amber-800">No supervisor is running.</span> Queued
            runs and agent turns wait until one is started:{" "}
            <code className="font-mono text-xs">make worker</code>
          </p>
        )}
      </div>

      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent className="sm:max-w-lg">
          <TrustForm project={project} onDone={() => setAsking(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

function TrustForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const id = useId()
  const trust = useTrustExecution(project.id)
  const [understood, setUnderstood] = useState(false)
  const [error, setError] = useState<unknown>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    trust.mutate(
      // The exact path is repeated: permission is given to a directory, not to a project name.
      { version: project.version, root_path: project.root_path ?? "" },
      { onSuccess: onDone, onError: setError },
    )
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Allow execution in the project directory</DialogTitle>
        <DialogDescription>
          Experiments of this project will run commands in this directory, as you, without a
          sandbox:
        </DialogDescription>
      </DialogHeader>
      <p className="rounded-md border border-border bg-muted/50 px-3 py-2 font-mono text-sm break-all">
        {project.root_path}
      </p>
      <p className="text-sm text-muted-foreground">
        The permission holds for this exact path. Changing the project&apos;s code path withdraws
        it. NumericOS only reads the repository: it never checks out, resets or commits.
      </p>
      <label htmlFor={`${id}-understood`} className="flex items-start gap-2 text-sm">
        <input
          id={`${id}-understood`}
          type="checkbox"
          className="mt-0.5"
          checked={understood}
          onChange={(event) => setUnderstood(event.target.checked)}
        />
        I know what the code in this directory does and want NumericOS to execute it.
      </label>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
        <Button type="submit" disabled={!understood || trust.isPending}>
          Allow execution
        </Button>
      </DialogFooter>
    </form>
  )
}
