import { useMemo, useState } from "react"
import type { DescribeRequest, FileCategory } from "@/api/client"
import { useDescribeFiles, useFiles } from "@/api/queries"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { useAgentReadiness } from "@/components/agent/readiness"
import { ErrorPanel } from "@/components/ErrorPanel"
import { FileRow } from "@/components/files/FileRow"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { describeError } from "@/lib/errors"
import { CATEGORIES, CATEGORY_LABELS, groupByDirectory } from "@/lib/files"
import { useProjectContext } from "@/pages/projectContext"

/**
 * The files of the project with what the agent wrote about each one. A description is kept
 * with the content it was written from: when the file changes, it is marked and can be asked
 * for again. Nothing is asked of the agent until a button says so.
 */
export function FilesView() {
  const { project, live, offline } = useProjectContext()
  const readiness = useAgentReadiness(project, offline)
  const trusted = project.root_path !== null && Boolean(project.execution_trusted_at)
  const files = useFiles(project.id, live, trusted)
  const describe = useDescribeFiles(project.id)
  const [notice, setNotice] = useState<string | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState<FileCategory | "all">("all")
  const [instructions, setInstructions] = useState("")
  const [opened, setOpened] = useState<string | null>(null)

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (files.data?.files ?? []).filter(
      (file) =>
        (category === "all" || file.category === category) &&
        (needle === "" || file.path.toLowerCase().includes(needle)),
    )
  }, [files.data, query, category])

  function ask(selection: Pick<DescribeRequest, "paths" | "scope">) {
    setSaid(null)
    describe.mutate(
      { ...selection, ...(instructions.trim() ? { instructions: instructions.trim() } : {}) },
      {
        onSuccess: (answer) =>
          setSaid(
            answer.queued === 0
              ? "Nothing to ask: those files are being described already."
              : `Asked the agent to describe ${answer.queued} ${answer.queued === 1 ? "file" : "files"} in ${answer.turns} ${answer.turns === 1 ? "turn" : "turns"}.` +
                  (answer.left > 0 ? ` ${answer.left} more are beyond one request: ask again after these.` : ""),
          ),
        onError: (error) => setNotice(describeError(error)),
      },
    )
  }

  const counts = files.data?.counts
  const toDescribe = (counts?.undescribed ?? 0) + (counts?.failed ?? 0)
  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      <AgentPreconditions project={project} offline={offline} readiness={readiness} />

      {!trusted ? (
        <p className="text-sm text-muted-foreground">
          The files are listed once the project has a code path and execution is allowed in it.
        </p>
      ) : files.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Reading the files of the project…
        </p>
      ) : files.isError ? (
        <ErrorPanel
          title="Could not list the files"
          error={files.error}
          onRetry={() => void files.refetch()}
        />
      ) : (
        <>
          <section
            aria-label="Descriptions of the files"
            className="space-y-3 rounded-lg border border-border bg-card p-4"
          >
            <p className="text-sm" data-testid="file-counts">
              <span className="font-medium">{counts!.total} files</span>
              <span className="text-muted-foreground">
                {" "}
                · {counts!.described} described · {counts!.stale} changed since ·{" "}
                {counts!.generating} being described · {toDescribe} not described
              </span>
              {files.data.truncated && (
                <span className="text-amber-800"> · only the first {counts!.total} are listed</span>
              )}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                disabled={readiness.blocked !== null || describe.isPending || toDescribe === 0}
                onClick={() => ask({ scope: "undescribed" })}
              >
                Describe the {toDescribe} not described
              </Button>
              <Button
                variant="outline"
                disabled={readiness.blocked !== null || describe.isPending || counts!.stale === 0}
                onClick={() => ask({ scope: "stale" })}
              >
                Update the {counts!.stale} changed
              </Button>
              <Input
                aria-label="Instructions for the agent"
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                placeholder="Instructions for the agent (optional): a language, an emphasis…"
                className="min-w-64 flex-1"
                maxLength={5000}
              />
            </div>
            {said && (
              <p role="status" className="text-sm text-muted-foreground">
                {said}
              </p>
            )}
            {readiness.blocked && (
              <p role="status" className="text-sm text-amber-800">
                {readiness.blocked}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              The agent reads a few files per turn and only reads. Which model it uses is the
              &quot;File descriptions&quot; row of Models and effort per task, in the Agent view.
            </p>
          </section>

          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label="Filter by path"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by path"
              className="max-w-xs"
            />
            <NativeSelect
              aria-label="Filter by kind"
              className="w-44"
              value={category}
              onChange={(event) => setCategory(event.target.value as FileCategory | "all")}
            >
              <NativeSelectOption value="all">All kinds</NativeSelectOption>
              {CATEGORIES.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {CATEGORY_LABELS[item]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <span className="text-xs text-muted-foreground">
              {shown.length} of {counts!.total} shown
            </span>
          </div>

          {shown.length === 0 ? (
            <p className="text-sm text-muted-foreground">No file matches.</p>
          ) : (
            <div className="space-y-4">
              {groupByDirectory(shown).map((group) => (
                <section
                  key={group.directory}
                  aria-label={group.directory || "Top of the project"}
                  className="overflow-hidden rounded-lg border border-border bg-card"
                >
                  <h3 className="border-b border-border bg-muted/50 px-3 py-1.5 font-mono text-xs text-muted-foreground">
                    {group.directory ? `${group.directory}/` : "(top of the project)"}
                  </h3>
                  <ul>
                    {group.files.map((file) => (
                      <FileRow
                        key={file.path}
                        projectId={project.id}
                        file={file}
                        open={opened === file.path}
                        onToggle={() => setOpened(opened === file.path ? null : file.path)}
                        blocked={readiness.blocked}
                        busy={describe.isPending}
                        onDescribe={() => ask({ paths: [file.path] })}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
