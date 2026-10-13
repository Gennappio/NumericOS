import { useState } from "react"
import { useGeneratePipeline, usePipeline } from "@/api/queries"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { useAgentReadiness } from "@/components/agent/readiness"
import { DocumentFooter } from "@/components/documents/DocumentFooter"
import { GenerateForm } from "@/components/documents/GenerateForm"
import { GenerationProgress } from "@/components/documents/GenerationProgress"
import { StaleNotice } from "@/components/documents/StaleNotice"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
import { PipelineBoard } from "@/components/pipeline/PipelineBoard"
import { describeError } from "@/lib/errors"
import { useProjectContext } from "@/pages/projectContext"

/**
 * What happens when the program of the project runs, drawn as a board: a box for every part
 * of the software, with its description, and arrows for what passes from one part to the
 * next. The agent writes it from the code, without running or changing anything; the page
 * says so when the code has changed since, and marks the boxes it concerns.
 */
export function PipelineView() {
  const { project, live, offline } = useProjectContext()
  const readiness = useAgentReadiness(project, offline)
  const pipeline = usePipeline(project.id, live)
  const generate = useGeneratePipeline(project.id)
  const [notice, setNotice] = useState<string | null>(null)
  const onError = (error: unknown) => setNotice(describeError(error))
  const document = pipeline.data?.document ?? null
  const drawn = document && document.version > 0 ? document.pipeline : null

  function ask(instructions: string) {
    generate.mutate(instructions, { onError })
  }

  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      <AgentPreconditions project={project} offline={offline} readiness={readiness} />

      {pipeline.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading the pipeline…
        </p>
      ) : pipeline.isError ? (
        <ErrorPanel
          title="Could not load the pipeline"
          error={pipeline.error}
          onRetry={() => void pipeline.refetch()}
        />
      ) : (
        <>
          {document?.pending_message_id && (
            <GenerationProgress
              projectId={project.id}
              messageId={document.pending_message_id}
              sessionId={document.session_id}
              label={document.version === 0 ? "Drawing the pipeline" : "Drawing the pipeline again"}
              supervisorAlive={readiness.supervisorAlive}
              onError={onError}
            />
          )}

          {document && drawn ? (
            <div className="space-y-4">
              <StaleNotice document={document}>
                What follows describes the program as it was; the boxes of the files that
                changed are marked. Draw it again below.
              </StaleNotice>
              {document.status_reason && (
                <p
                  role="alert"
                  className="rounded-lg border border-border bg-muted/50 px-4 py-2 text-sm"
                >
                  The last request to draw it again did not succeed: {document.status_reason}.
                  What follows is the version before.
                </p>
              )}
              {/* Keyed by version: a pipeline drawn again is another board. */}
              <PipelineBoard
                key={document.version}
                projectId={project.id}
                document={document}
                pipeline={drawn}
                blocked={readiness.blocked}
                supervisorAlive={readiness.supervisorAlive}
                onError={onError}
              />
              <DocumentFooter
                projectId={project.id}
                document={document}
                name="pipeline"
                again="Draw it again"
                action="Draw the pipeline again"
                blocked={readiness.blocked}
                pending={generate.isPending || Boolean(document.pending_message_id)}
                onGenerate={ask}
              />
            </div>
          ) : (
            !document?.pending_message_id && (
              <section className="space-y-4 rounded-lg border border-dashed border-border p-6">
                <div className="max-w-prose space-y-2">
                  <h2 className="text-base font-medium">The pipeline of this project</h2>
                  <p className="text-sm text-muted-foreground">
                    The agent reads the repository and draws what happens when the program runs:
                    a box for every part of the software (what it reads, each stage of the
                    computation, what it writes), each with its description and its files, and
                    arrows for what passes from one part to the next. It only reads: nothing is
                    run and no file is changed. Any text of a box can then be commented, as in
                    the other pages.
                  </p>
                  {document?.status === "failed" && (
                    <p role="alert" className="text-sm text-red-800">
                      The last request did not produce a pipeline: {document.status_reason}
                    </p>
                  )}
                </div>
                <GenerateForm
                  action="Draw the pipeline"
                  instructions={document?.instructions ?? ""}
                  blocked={readiness.blocked}
                  pending={generate.isPending}
                  hint="For example: Scrivi in italiano. Un riquadro per ogni fase del ciclo temporale."
                  onGenerate={ask}
                />
              </section>
            )
          )}
        </>
      )}
    </div>
  )
}
