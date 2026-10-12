import { Link, useParams } from "react-router"
import type { Experiment, ExperimentSeries, Run } from "@/api/client"
import {
  isActive,
  useExperiment,
  useExperimentRuns,
  useExperimentSeries,
  useWorkers,
} from "@/api/queries"
import { ErrorPanel } from "@/components/ErrorPanel"
import { RunForm } from "@/components/experiments/RunForm"
import { RunsTable, type RunColumn } from "@/components/runs/RunsTable"
import { Section } from "@/components/Section"
import { formatValue, shortHash } from "@/lib/format"
import { describeRule } from "@/lib/protocol"
import { useProjectContext } from "@/pages/projectContext"

/** One experiment: its contract in words, the form that queues a run, and its runs side by side. */
export function ExperimentView() {
  const { experimentId = "" } = useParams()
  const { project, offline } = useProjectContext()
  const experiment = useExperiment(project.id, experimentId)
  const runs = useExperimentRuns(project.id, experimentId)
  const active = runs.data?.runs.some((run) => isActive(run.status)) ?? false
  const series = useExperimentSeries(project.id, experimentId, active)
  const workers = useWorkers()

  if (experiment.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading experiment…
      </p>
    )
  }
  if (experiment.isError) {
    return (
      <ErrorPanel
        title="Could not load the experiment"
        error={experiment.error}
        onRetry={() => void experiment.refetch()}
      />
    )
  }

  const data = experiment.data
  const protocol = data.protocol
  const blocked = offline
    ? "The backend is not reachable."
    : !project.execution_trusted_at
      ? "Execution in the project directory is not allowed yet: see the Experiments view."
      : undefined
  const noSupervisor = workers.data !== undefined && workers.data.alive === 0

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <p className="text-sm">
          <Link to={`/projects/${project.id}/experiments`} className="underline underline-offset-4">
            Experiments
          </Link>{" "}
          <span className="text-muted-foreground">/ {data.name}</span>
        </p>
        <h2 className="text-xl font-semibold break-words">{data.name}</h2>
        <p className="max-w-prose text-base break-words">{protocol.question}</p>
        <p className="text-xs text-muted-foreground">
          Contract{" "}
          <span className="font-mono" title={data.protocol_digest}>
            {shortHash(data.protocol_digest)}
          </span>
          {data.run_count > 0 && " · frozen: it has runs, so it can no longer change"}
        </p>
      </header>

      <ContractSummary experiment={data} />

      <Section
        title="Run it"
        description="A run executes the contract with one declared value for each variable. It returns at once; a supervisor executes it."
      >
        {noSupervisor && (
          <p className="text-sm text-amber-800">
            No supervisor is running: a queued run waits until one is started (
            <code className="font-mono text-xs">make worker</code>).
          </p>
        )}
        <RunForm projectId={project.id} experiment={data} blocked={blocked} />
      </Section>

      <Section
        title="Runs"
        description="Every run of this experiment, with the last value of each declared metric. A value is what was measured, not a verdict."
      >
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
          <p className="text-sm text-muted-foreground">This experiment has not been run yet.</p>
        ) : (
          <RunsTable
            projectId={project.id}
            // Newest first: the run just queued is at the top.
            runs={[...runs.data.runs].reverse()}
            columns={comparisonColumns(data, series.data?.series ?? [])}
            caption={`Runs of ${data.name}`}
          />
        )}
      </Section>
    </div>
  )
}

/** One column per independent variable, then one per declared metric with its last value. */
function comparisonColumns(experiment: Experiment, series: ExperimentSeries[]): RunColumn[] {
  const byRun = new Map<string, Map<string, ExperimentSeries>>()
  for (const item of series) {
    if (!byRun.has(item.run_id)) byRun.set(item.run_id, new Map())
    byRun.get(item.run_id)!.set(item.name, item)
  }
  const variables = Object.keys(experiment.protocol.independent_variables ?? {})
  const metrics = experiment.protocol.metrics ?? []
  return [
    ...variables.map<RunColumn>((name) => ({
      title: name,
      numeric: true,
      cell: (run: Run) => String(run.parameters[name] ?? "–"),
    })),
    ...metrics.map<RunColumn>((metric) => ({
      title: metric.unit ? `${metric.name} [${metric.unit}]` : metric.name,
      numeric: true,
      cell: (run: Run) => {
        const found = byRun.get(run.id)?.get(metric.name)
        if (!found) return <span className="text-muted-foreground">–</span>
        return (
          <span
            className={found.non_finite ? "text-red-700" : undefined}
            title={
              found.non_finite
                ? `${found.non_finite} of ${found.samples} samples were not finite`
                : `${found.samples} samples`
            }
          >
            {formatValue(found.last_value, found.last_non_finite)}
          </span>
        )
      },
    })),
  ]
}

function ContractSummary({ experiment }: { experiment: Experiment }) {
  const protocol = experiment.protocol
  const execution = protocol.execution
  const controls = Object.entries(protocol.controls ?? {})
  const variables = Object.entries(protocol.independent_variables ?? {})
  const metrics = protocol.metrics ?? []
  const rules = protocol.guardrails?.rules ?? []
  const parsers = protocol.observability?.parsers ?? []
  const nonFinite = protocol.guardrails?.non_finite ?? "record"
  const code = execution.code?.mode ?? "ref"

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="What it asks">
        <dl className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm">
          {protocol.prediction && (
            <div>
              <dt className="text-xs font-medium text-muted-foreground uppercase">Prediction</dt>
              <dd className="break-words">{protocol.prediction}</dd>
            </div>
          )}
          {(protocol.falsification ?? []).length > 0 && (
            <div>
              <dt className="text-xs font-medium text-muted-foreground uppercase">
                Would contradict it
              </dt>
              <dd>
                <ul className="list-disc pl-5">
                  {protocol.falsification!.map((item) => (
                    <li key={item} className="break-words">
                      {item}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
          <div>
            <dt className="text-xs font-medium text-muted-foreground uppercase">Varies</dt>
            <dd className="font-mono text-xs">
              {variables.length === 0
                ? "nothing"
                : variables.map(([name, values]) => `${name} in [${values.join(", ")}]`).join("; ")}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground uppercase">Stays fixed</dt>
            <dd className="font-mono text-xs">
              {controls.length === 0
                ? "nothing"
                : controls.map(([name, value]) => `${name}=${String(value)}`).join("  ")}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="What a run does">
        <dl className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm">
          <div>
            <dt className="text-xs font-medium text-muted-foreground uppercase">Command</dt>
            <dd className="font-mono text-xs break-all">{execution.command.join(" ")}</dd>
          </div>
          {(execution.build ?? []).length > 0 && (
            <div>
              <dt className="text-xs font-medium text-muted-foreground uppercase">Built first with</dt>
              <dd className="font-mono text-xs break-all">
                {execution.build!.map((command) => (
                  <div key={command.join(" ")}>{command.join(" ")}</div>
                ))}
              </dd>
            </div>
          )}
          <div>
            <dt className="text-xs font-medium text-muted-foreground uppercase">Code</dt>
            <dd>
              {code === "ref"
                ? `An exact commit (default ${execution.code?.ref ?? "HEAD"}), exported for the run. Uncommitted edits are not part of it.`
                : "The working tree as it is when the run starts, uncommitted edits included. They are recorded as a patch."}{" "}
              <span className="text-muted-foreground">
                Working directory: <span className="font-mono text-xs">{execution.workdir ?? "."}</span>
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground uppercase">Limits</dt>
            <dd>
              {protocol.limits.wall_seconds} s wall clock
              {typeof protocol.limits.max_rss_mb === "number" &&
                `, ${protocol.limits.max_rss_mb} MB of memory`}
            </dd>
          </div>
        </dl>
      </Section>

      <Section
        title="What is measured"
        description="Each metric says who measures it: the program itself, a parser of its output, or the supervisor from outside."
      >
        {metrics.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            The contract declares no metric: only the process of a run is observed.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Metric</th>
                  <th scope="col" className="px-3 py-2 font-medium">Unit</th>
                  <th scope="col" className="px-3 py-2 font-medium">Measured by</th>
                  <th scope="col" className="px-3 py-2 font-medium">What it is</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {metrics.map((metric) => (
                  <tr key={metric.name} className="align-top">
                    <td className="px-3 py-2 font-mono text-xs">{metric.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{metric.unit || "–"}</td>
                    <td className="px-3 py-2">{metric.sampled_by}</td>
                    <td className="px-3 py-2 text-muted-foreground">{metric.description ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {parsers.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Output parsers: {parsers.map((parser) => parser.name).join(", ")}
          </p>
        )}
      </Section>

      <Section
        title="What stops a run"
        description="Only bounds the contract states. NumericOS assumes no threshold."
      >
        <ul className="space-y-1 rounded-lg border border-border bg-card p-4 text-sm">
          <li>
            A metric that becomes NaN or infinite:{" "}
            {nonFinite === "halt" ? "the program is stopped" : "an error is recorded, the run goes on"}
          </li>
          {rules.map((rule) => (
            <li key={describeRule(rule)}>{describeRule(rule)}</li>
          ))}
          <li>More than {protocol.limits.wall_seconds} s of wall-clock time: the program is stopped</li>
        </ul>
      </Section>
    </div>
  )
}
