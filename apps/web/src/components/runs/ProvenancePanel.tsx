import type { ReactNode } from "react"
import { runRecordUrl, type Run } from "@/api/client"
import { formatBytes } from "@/lib/format"
import { formatParameters } from "@/lib/runs"
import { formatEventTime } from "@/lib/time"

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 px-3 py-2 sm:grid-cols-[11rem_1fr]">
      <dt className="text-xs font-medium text-muted-foreground uppercase">{term}</dt>
      <dd className="min-w-0 text-sm break-words">{children}</dd>
    </div>
  )
}

const Mono = ({ children }: { children: ReactNode }) => (
  <span className="font-mono text-xs break-all">{children}</span>
)

/**
 * Exactly what ran: the code, the command, the program file, the inputs and the machine. These
 * are recorded facts of the run, enough for someone else to repeat it.
 */
export function ProvenancePanel({ run }: { run: Run }) {
  const code = run.code
  const environment = run.environment
  return (
    <dl className="divide-y divide-border rounded-lg border border-border bg-card">
      <Row term="Code">
        {!code ? (
          "Not recorded"
        ) : code.mode === "ref" ? (
          <>
            Commit <Mono>{code.sha}</Mono>
            {code.commit && (
              <span className="text-muted-foreground">
                {" "}
                · {code.commit.subject} · {code.commit.author},{" "}
                {formatEventTime(code.commit.authored_at)}
              </span>
            )}
            <div className="text-muted-foreground">
              Asked for as <Mono>{code.requested_ref}</Mono>, fixed to this commit when the run was
              queued, and exported for the run.
              {code.submitted_with_dirty_working_tree &&
                " The working tree had uncommitted changes at that moment: they were not executed."}
            </div>
          </>
        ) : code.sha === null || code.sha === undefined ? (
          "The working tree, recorded when the run starts"
        ) : (
          <>
            Working tree on commit <Mono>{code.sha}</Mono>
            <div className="text-muted-foreground">
              {code.dirty
                ? `With uncommitted changes, kept as a patch${code.diff_sha256 ? ` (SHA-256 ${code.diff_sha256.slice(0, 12)}…)` : ""}`
                : "Without uncommitted changes"}
              {(code.untracked ?? []).length > 0 &&
                ` and ${code.untracked!.length} untracked ${code.untracked!.length === 1 ? "file" : "files"}${code.untracked_archived ? ", archived with the run" : ", too large to be stored"}`}
              .
            </div>
            {code.changed_during_run && (
              <div className="font-medium text-amber-800">
                The source was edited while the program ran: this record describes what it started
                with.
              </div>
            )}
          </>
        )}
      </Row>
      <Row term="Repository">
        <Mono>{code?.repository_root ?? "–"}</Mono>
        {code?.remote_url && <span className="text-muted-foreground"> · {code.remote_url}</span>}
      </Row>
      <Row term="Command">
        <Mono>{run.argv.join(" ")}</Mono>
      </Row>
      <Row term="Parameters">
        <Mono>{formatParameters(run.parameters)}</Mono>
        {typeof run.seed === "number" && <span> · seed {run.seed}</span>}
      </Row>
      <Row term="Contract">
        <Mono>{run.protocol_digest}</Mono>
      </Row>
      <Row term="Program file">
        {environment?.executable.path ? (
          <>
            <Mono>{environment.executable.path}</Mono>
            {environment.executable.sha256 && (
              <div className="text-muted-foreground">
                SHA-256 <Mono>{environment.executable.sha256}</Mono>
                {typeof environment.executable.size_bytes === "number" &&
                  ` · ${formatBytes(environment.executable.size_bytes)}`}
              </div>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">
            {run.started_at ? "Could not be resolved" : "Identified when the program starts"}
          </span>
        )}
      </Row>
      <Row term="Inputs">
        {(run.inputs ?? []).length === 0 ? (
          <span className="text-muted-foreground">
            {run.inputs ? "The contract declares none" : "Checked when the run starts"}
          </span>
        ) : (
          <ul>
            {run.inputs!.map((input) => (
              <li key={`${input.base}/${input.path}`}>
                <Mono>{input.path}</Mono>{" "}
                <span className="text-muted-foreground">
                  · {formatBytes(input.size_bytes)} · SHA-256 <Mono>{input.sha256}</Mono>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Row>
      <Row term="Machine">
        {environment ? (
          <>
            {environment.host.processor}, {environment.host.cpu_count_physical ?? "?"} cores (
            {environment.host.cpu_count_logical ?? "?"} logical),{" "}
            {formatBytes(environment.host.memory_total_bytes)} of memory
            <div className="text-muted-foreground">
              {environment.host.platform} · {environment.host.hostname}
            </div>
          </>
        ) : (
          <span className="text-muted-foreground">Recorded when the run starts</span>
        )}
      </Row>
      {(environment?.probes ?? []).length > 0 && (
        <Row term="Environment probes">
          <ul>
            {environment!.probes!.map((probe) => (
              <li key={probe.argv.join(" ")}>
                <Mono>{probe.argv.join(" ")}</Mono>{" "}
                <span className="text-muted-foreground">
                  {probe.exit_code === null || probe.exit_code === undefined
                    ? `could not be run: ${probe.error ?? "unknown reason"}`
                    : `exit code ${probe.exit_code}, output kept as ${probe.output_file ?? "an artifact"}`}
                </span>
              </li>
            ))}
          </ul>
        </Row>
      )}
      {environment && (
        <Row term="Environment variables">
          <details>
            <summary className="cursor-pointer text-sm">
              {Object.keys(environment.variables ?? {}).length} variables reached the program
            </summary>
            <ul className="mt-1 font-mono text-xs break-all">
              {Object.entries(environment.variables ?? {}).map(([name, value]) => (
                <li key={name}>
                  {name}={value}
                </li>
              ))}
            </ul>
          </details>
        </Row>
      )}
      {run.reproduces_run_id && (
        <Row term="Repeats">
          <Mono>{run.reproduces_run_id}</Mono>
        </Row>
      )}
      <Row term="Run record">
        <a
          href={runRecordUrl(run.id)}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-4"
        >
          Everything above with the contract, as JSON
        </a>
      </Row>
    </dl>
  )
}
