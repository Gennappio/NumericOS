import { useState } from "react"
import { useAgentPolicy } from "@/api/queries"
import { PolicyPanel } from "@/components/agent/PolicyPanel"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { useAgentReadiness } from "@/components/agent/readiness"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
import { Section } from "@/components/Section"
import { describeError } from "@/lib/errors"
import { useProjectContext } from "@/pages/projectContext"

/**
 * How the coding agent is used in this project: which model answers each kind of task, and
 * how hard it tries. The conversations themselves are under the project's name in the sidebar.
 */
export function AgentView() {
  const { project, live, offline } = useProjectContext()
  const readiness = useAgentReadiness(project, offline)
  const policy = useAgentPolicy(project.id, live)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}

      <AgentPreconditions project={project} offline={offline} readiness={readiness} />

      <Section
        title="Models and effort per task"
        description="Which model answers each kind of task of this project, and how hard it tries. A lighter model on the tasks that are asked often spares your plan."
      >
        <div className="max-w-4xl">
          {policy.data ? (
            <PolicyPanel
              key={policy.data.version}
              projectId={project.id}
              policy={policy.data}
              capabilities={readiness.capabilities}
              disabled={offline}
              onError={(error) => setNotice(describeError(error))}
            />
          ) : policy.isError ? (
            <ErrorPanel
              title="Could not load the policy"
              error={policy.error}
              onRetry={() => void policy.refetch()}
            />
          ) : (
            <p role="status" className="text-sm text-muted-foreground">
              Loading…
            </p>
          )}
        </div>
      </Section>
    </div>
  )
}
