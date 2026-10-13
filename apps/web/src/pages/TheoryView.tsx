import { useState, type ReactNode } from "react"
import { fileContentUrl, type DocumentOut } from "@/api/client"
import { useGenerateTheory, useTheory } from "@/api/queries"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { Commentable } from "@/components/comments/Commentable"
import { useAgentReadiness } from "@/components/agent/readiness"
import { DocumentFooter } from "@/components/documents/DocumentFooter"
import { GenerateForm } from "@/components/documents/GenerateForm"
import { GenerationProgress } from "@/components/documents/GenerationProgress"
import { StaleNotice } from "@/components/documents/StaleNotice"
import { ErrorPanel } from "@/components/ErrorPanel"
import { shareTheory } from "@/components/export/exportDocument"
import { ShareButton } from "@/components/export/ShareButton"
import { Notice } from "@/components/Notice"
import { describeError } from "@/lib/errors"
import { useProjectContext } from "@/pages/projectContext"

/**
 * The theory of the project as the agent wrote it from the code: the model, the numerical
 * method, how each element maps to the code. It is rendered like a paper, says which files it
 * was written from, and says so when one of them has changed since.
 */
export function TheoryView() {
  const { project, live, offline } = useProjectContext()
  const readiness = useAgentReadiness(project, offline)
  const theory = useTheory(project.id, live)
  const generate = useGenerateTheory(project.id)
  const [notice, setNotice] = useState<string | null>(null)
  const onError = (error: unknown) => setNotice(describeError(error))
  const document = theory.data?.document ?? null

  function ask(instructions: string) {
    generate.mutate(instructions, { onError })
  }

  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      <AgentPreconditions project={project} offline={offline} readiness={readiness} />

      {theory.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading the theory…
        </p>
      ) : theory.isError ? (
        <ErrorPanel
          title="Could not load the theory"
          error={theory.error}
          onRetry={() => void theory.refetch()}
        />
      ) : (
        <>
          {document?.pending_message_id && (
            <GenerationProgress
              projectId={project.id}
              messageId={document.pending_message_id}
              sessionId={document.session_id}
              label={document.version === 0 ? "Writing the theory" : "Writing the theory again"}
              supervisorAlive={readiness.supervisorAlive}
              onError={onError}
            />
          )}

          {!document || (document.version === 0 && !document.pending_message_id) ? (
            <section className="space-y-4 rounded-lg border border-dashed border-border p-6">
              <div className="max-w-prose space-y-2">
                <h2 className="text-base font-medium">The theory of this project</h2>
                <p className="text-sm text-muted-foreground">
                  The agent reads the repository and writes what the project computes as a short
                  paper: the problem, the mathematical model, the numerical method, its
                  properties, how each element maps to the code, inputs and outputs, and what
                  is assumed. It only reads: no file is changed.
                </p>
                {document?.status === "failed" && (
                  <p role="alert" className="text-sm text-red-800">
                    The last request did not produce a document: {document.status_reason}
                  </p>
                )}
              </div>
              <GenerateForm
                action="Write the theory"
                instructions={document?.instructions ?? ""}
                blocked={readiness.blocked}
                pending={generate.isPending}
                hint="For example: Scrivi in italiano. Concentrati sulla stabilità dello schema."
                onGenerate={ask}
              />
            </section>
          ) : (
            document.version > 0 && (
              <Paper
                projectId={project.id}
                document={document}
                blocked={readiness.blocked}
                supervisorAlive={readiness.supervisorAlive}
                pending={generate.isPending || Boolean(document.pending_message_id)}
                actions={
                  <ShareButton
                    build={() => shareTheory(project, document)}
                    onNotice={setNotice}
                    onError={onError}
                  />
                }
                onGenerate={ask}
                onError={onError}
              />
            )
          )}
        </>
      )}
    </div>
  )
}

interface PaperProps {
  projectId: string
  document: DocumentOut
  blocked: string | null
  supervisorAlive: boolean
  pending: boolean
  /** What can be done with the whole text: shown above it. */
  actions: ReactNode
  onGenerate: (instructions: string) => void
  onError: (error: unknown) => void
}

function Paper({
  projectId,
  document,
  blocked,
  supervisorAlive,
  pending,
  actions,
  onGenerate,
  onError,
}: PaperProps) {
  return (
    <div className="space-y-4">
      <div className="flex justify-end">{actions}</div>
      <StaleNotice document={document}>
        What follows describes the project as it was. Write it again below.
      </StaleNotice>
      {document.status_reason && (
        <p role="alert" className="rounded-lg border border-border bg-muted/50 px-4 py-2 text-sm">
          The last request to write it again did not succeed: {document.status_reason}. What
          follows is the version before.
        </p>
      )}

      {/* Keyed by version: a text written again starts without a half-written comment. */}
      <Commentable
        key={document.version}
        projectId={projectId}
        target={{ type: "document", id: document.id }}
        source={document.markdown}
        version={document.version}
        className="paper"
        boxClassName="rounded-lg border border-border bg-card px-6 py-10 md:px-12"
        label={document.title || "Theory"}
        resolveImage={(path) => fileContentUrl(projectId, path)}
        layout="side"
        blocked={blocked}
        supervisorAlive={supervisorAlive}
        onError={onError}
      />

      <DocumentFooter
        projectId={projectId}
        document={document}
        name="theory"
        again="Write it again"
        action="Write the theory again"
        blocked={blocked}
        pending={pending}
        onGenerate={onGenerate}
      />
    </div>
  )
}
