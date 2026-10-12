import type { Project } from "@/api/client"
import type { AgentReadiness } from "@/components/agent/readiness"
import { ExecutionPanel } from "@/components/experiments/ExecutionPanel"
import { Section } from "@/components/Section"
import { describeError } from "@/lib/errors"

interface PreconditionsProps {
  project: Project
  offline: boolean
  readiness: AgentReadiness
}

/** Shown only while something stands between the agent and its work, saying what. */
export function AgentPreconditions({ project, offline, readiness }: PreconditionsProps) {
  if (readiness.blocked === null && readiness.supervisorAlive) return null
  const { capabilities, capabilitiesError } = readiness
  return (
    <Section title="Before the agent can work">
      <div className="space-y-3">
        <ExecutionPanel project={project} disabled={offline} purpose="agent" />
        <div
          data-state={
            capabilities ? (capabilities.available ? "available" : "unavailable") : "checking"
          }
          className="space-y-1 rounded-lg border border-border bg-card p-4"
        >
          <h3 className="text-sm font-medium">Coding agent</h3>
          {capabilities ? (
            capabilities.available ? (
              <p className="text-sm">
                Claude Code {capabilities.version}{" "}
                <span className="font-mono text-xs break-all text-muted-foreground">
                  {capabilities.path}
                </span>
              </p>
            ) : (
              <p className="text-sm">
                <span className="font-medium text-amber-800">Not available.</span>{" "}
                {capabilities.problem}
              </p>
            )
          ) : capabilitiesError ? (
            <p className="text-sm text-muted-foreground">{describeError(capabilitiesError)}</p>
          ) : (
            <p role="status" className="text-sm text-muted-foreground">
              Checking…
            </p>
          )}
        </div>
      </div>
    </Section>
  )
}
