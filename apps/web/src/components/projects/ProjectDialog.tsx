import { useId, useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import type { Project } from "@/api/client"
import { useCreateProject, useUpdateProject } from "@/api/queries"
import { FormField } from "@/components/FormField"
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
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { describeError, fieldErrors } from "@/lib/errors"

interface ProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Edit this project; omit to create a new one. */
  project?: Project
}

export function ProjectDialog({ open, onOpenChange, project }: ProjectDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* The form mounts with the dialog, so every opening starts from the current project. */}
        <ProjectForm project={project} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

function ProjectForm({ project, onDone }: { project?: Project; onDone: () => void }) {
  const id = useId()
  const navigate = useNavigate()
  const [name, setName] = useState(project?.name ?? "")
  const [question, setQuestion] = useState(project?.research_question ?? "")
  const [description, setDescription] = useState(project?.description ?? "")
  const [rootPath, setRootPath] = useState(project?.root_path ?? "")
  const [error, setError] = useState<unknown>(null)
  const createProject = useCreateProject()
  const updateProject = useUpdateProject(project?.id ?? "")
  const pending = createProject.isPending || updateProject.isPending
  const errors = fieldErrors(error)
  const generalError = error !== null && Object.keys(errors).length === 0

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const fields = {
      name: name.trim(),
      research_question: question.trim(),
      description: description.trim(),
      root_path: rootPath.trim() || null,
    }
    if (project) {
      updateProject.mutate(
        { version: project.version, ...fields },
        { onSuccess: onDone, onError: setError },
      )
    } else {
      createProject.mutate(fields, {
        onSuccess: (created) => {
          onDone()
          navigate(`/projects/${created.id}`)
        },
        onError: setError,
      })
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{project ? "Edit project" : "New project"}</DialogTitle>
        <DialogDescription>
          A project gathers the hypotheses, experiments, issues and decisions around one research
          question.
        </DialogDescription>
      </DialogHeader>

      <FormField id={`${id}-name`} label="Name" error={errors.name}>
        <Input
          id={`${id}-name`}
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={200}
          aria-invalid={errors.name ? true : undefined}
        />
      </FormField>
      <FormField
        id={`${id}-question`}
        label="Research question"
        hint="What this project is trying to find out."
        error={errors.research_question}
      >
        <Textarea
          id={`${id}-question`}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={5000}
        />
      </FormField>
      <FormField id={`${id}-description`} label="Description" error={errors.description}>
        <Textarea
          id={`${id}-description`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={20000}
        />
      </FormField>
      <FormField
        id={`${id}-root-path`}
        label="Code reference"
        hint="Optional absolute path of the research code. Stored as a reference only: NumericOS does not open or run it yet."
        error={errors.root_path}
      >
        <Input
          id={`${id}-root-path`}
          value={rootPath}
          onChange={(event) => setRootPath(event.target.value)}
          placeholder="/absolute/path/to/solver"
          className="font-mono"
          aria-invalid={errors.root_path ? true : undefined}
        />
      </FormField>

      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}

      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
        <Button type="submit" disabled={pending}>
          {project ? "Save project" : "Create project"}
        </Button>
      </DialogFooter>
    </form>
  )
}
