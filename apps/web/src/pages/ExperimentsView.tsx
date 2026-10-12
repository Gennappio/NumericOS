import { useState } from "react"
import { Link } from "react-router"
import type { Experiment } from "@/api/client"
import { useExperiments, useProjectRuns } from "@/api/queries"
import { ErrorPanel } from "@/components/ErrorPanel"
import { ContractFiles } from "@/components/experiments/ContractFiles"
import { ExecutionPanel } from "@/components/experiments/ExecutionPanel"
import { Notice } from "@/components/Notice"
import { RunsTable } from "@/components/runs/RunsTable"
import { Section } from "@/components/Section"
import { shortHash } from "@/lib/format"
import { useProjectContext } from "@/pages/projectContext"

/** Experiments of a project: what can be run, whether it can run now, and what ran lately. */
export function ExperimentsView() {
  const { project, live, offline } = useProjectContext()
  const experiments = useExperiments(project.id, live)
  const runs = useProjectRuns(project.id)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="space-y-8">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}

      <Section title="Before anything runs">
        <ExecutionPanel project={project} disabled={offline} />
      </Section>

      <Section
        title="Experiments"
        description="An experiment is a contract: what is asked, what varies, how one run is executed, what is measured and which bounds stop a run."
      >
        {experiments.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading experiments…
          </p>
        ) : experiments.isError ? (
          <ErrorPanel
            title="Could not load the experiments"
            error={experiments.error}
            onRetry={() => void experiments.refetch()}
          />
        ) : experiments.data.experiments.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No experiment is registered yet. Register one from a contract file below.
          </p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {experiments.data.experiments.map((experiment) => (
              <ExperimentCard key={experiment.id} projectId={project.id} experiment={experiment} />
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Contracts in the repository"
        description="Files of the project directory that are experiment contracts."
      >
        <ContractFiles project={project} disabled={offline} onError={setNotice} />
      </Section>

      <Section title="Recent runs" description="The newest runs of all experiments of the project.">
        {runs.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading runs…
          </p>
        ) : runs.isError ? (
          <ErrorPanel
            title="Could not load the runs"
            error={runs.error}
            onRetry={() => void runs.refetch()}
          />
        ) : runs.data.runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing has been run yet.</p>
        ) : (
          <RunsTable projectId={project.id} runs={runs.data.runs} caption="Recent runs" />
        )}
      </Section>
    </div>
  )
}

function ExperimentCard({ projectId, experiment }: { projectId: string; experiment: Experiment }) {
  const variables = Object.entries(experiment.protocol.independent_variables ?? {})
  return (
    <li className="space-y-1 rounded-lg border border-border bg-card p-4">
      <Link
        to={`/projects/${projectId}/experiments/${experiment.id}`}
        className="font-medium underline underline-offset-4"
      >
        {experiment.name}
      </Link>
      <p className="text-sm break-words">{experiment.protocol.question}</p>
      <p className="text-xs text-muted-foreground">
        {variables.length === 0
          ? "Nothing varies between its runs"
          : variables.map(([name, values]) => `${name} in ${values.join(", ")}`).join("; ")}
      </p>
      <p className="text-xs text-muted-foreground">
        {experiment.run_count} {experiment.run_count === 1 ? "run" : "runs"} · contract{" "}
        <span className="font-mono" title={experiment.protocol_digest}>
          {shortHash(experiment.protocol_digest)}
        </span>
      </p>
    </li>
  )
}
