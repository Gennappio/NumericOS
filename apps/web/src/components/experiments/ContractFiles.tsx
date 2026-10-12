import { useId, useState, type FormEvent } from "react"
import { Link } from "react-router"
import type { ContractFile, Project } from "@/api/client"
import { useContractFiles, useImportExperiment } from "@/api/queries"
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
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/api/client"
import { describeError } from "@/lib/errors"

interface ContractFilesProps {
  project: Project
  disabled: boolean
  onError: (message: string) => void
}

/**
 * Experiment contracts found as files in the project's repository, each one click away from
 * being registered. Nothing is registered by looking: the list only reads the directory.
 */
export function ContractFiles({ project, disabled, onError }: ContractFilesProps) {
  const files = useContractFiles(project.id, project.root_path !== null)
  const [pasting, setPasting] = useState(false)

  return (
    <div className="space-y-3">
      {project.root_path === null ? (
        <p className="text-sm text-muted-foreground">
          Without a code path there is no repository to look in. A contract can still be pasted.
        </p>
      ) : files.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Looking for contract files…
        </p>
      ) : files.isError ? (
        <p role="alert" className="text-sm text-muted-foreground">
          {describeError(files.error)}
        </p>
      ) : files.data.files.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No file of the repository is an experiment contract (a YAML file with{" "}
          <code className="font-mono text-xs">schema: numericos.experiment.v1</code>).{" "}
          {files.data.scanned} YAML {files.data.scanned === 1 ? "file was" : "files were"} looked
          at.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {files.data.files.map((file) => (
            <ContractRow
              key={file.path}
              projectId={project.id}
              file={file}
              disabled={disabled}
              onError={onError}
            />
          ))}
        </ul>
      )}
      <Button variant="outline" onClick={() => setPasting(true)} disabled={disabled}>
        Paste a contract…
      </Button>

      <Dialog open={pasting} onOpenChange={setPasting}>
        <DialogContent className="sm:max-w-2xl">
          <PasteForm projectId={project.id} onDone={() => setPasting(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ContractRow({
  projectId,
  file,
  disabled,
  onError,
}: {
  projectId: string
  file: ContractFile
  disabled: boolean
  onError: (message: string) => void
}) {
  const register = useImportExperiment(projectId)
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 px-3 py-2">
      <div className="min-w-0 space-y-0.5">
        <p className="font-mono text-xs break-all">{file.path}</p>
        <p className="text-sm font-medium break-words">{file.name}</p>
        {file.question && <p className="text-sm text-muted-foreground">{file.question}</p>}
        {!file.valid && (
          <ul className="text-xs text-destructive">
            {file.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
      </div>
      {file.experiment_id ? (
        <Link
          to={`/projects/${projectId}/experiments/${file.experiment_id}`}
          className="shrink-0 text-sm underline underline-offset-4"
        >
          Registered: open
        </Link>
      ) : file.valid ? (
        <Button
          variant="outline"
          className="shrink-0"
          disabled={disabled || register.isPending}
          onClick={() =>
            register.mutate(
              { path: file.path, reuse: true },
              { onError: (error) => onError(describeError(error)) },
            )
          }
        >
          Register
        </Button>
      ) : (
        <span className="shrink-0 text-xs text-muted-foreground">Not a valid contract</span>
      )}
    </li>
  )
}

/** What the API said is wrong with a contract, one line per problem. */
function problems(error: unknown): string[] {
  if (error instanceof ApiError && Array.isArray(error.details.errors)) {
    return (error.details.errors as { loc?: unknown[]; msg?: unknown }[]).map((issue) => {
      const where = (issue.loc ?? []).slice(2).join(".")
      return where ? `${where}: ${String(issue.msg)}` : String(issue.msg)
    })
  }
  return [describeError(error)]
}

function PasteForm({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const id = useId()
  const register = useImportExperiment(projectId)
  const [text, setText] = useState("")
  const [error, setError] = useState<unknown>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    register.mutate({ text, reuse: true }, { onSuccess: onDone, onError: setError })
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Register an experiment from its contract</DialogTitle>
        <DialogDescription>
          A <code className="font-mono text-xs">numericos.experiment.v1</code> contract in YAML or
          JSON. It may carry the experiment&apos;s <code className="font-mono text-xs">name</code>.
        </DialogDescription>
      </DialogHeader>
      <label htmlFor={`${id}-text`} className="sr-only">
        Contract
      </label>
      <Textarea
        id={`${id}-text`}
        value={text}
        onChange={(event) => setText(event.target.value)}
        required
        spellCheck={false}
        className="h-72 font-mono text-xs"
        placeholder={"schema: numericos.experiment.v1\nname: my-experiment\nquestion: ...\n"}
      />
      {error !== null && (
        <ul role="alert" className="max-h-40 overflow-y-auto text-sm text-destructive">
          {problems(error).map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
        <Button type="submit" disabled={register.isPending || text.trim() === ""}>
          Register experiment
        </Button>
      </DialogFooter>
    </form>
  )
}
