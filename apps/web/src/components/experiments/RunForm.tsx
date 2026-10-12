import { useId, useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import type { Experiment } from "@/api/client"
import { useCreateRun } from "@/api/queries"
import { FormField } from "@/components/FormField"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { describeError, fieldErrors } from "@/lib/errors"
import { needsSeed } from "@/lib/protocol"

interface RunFormProps {
  projectId: string
  experiment: Experiment
  /** Why a run cannot be queued now, if it cannot. */
  blocked?: string
}

/**
 * Queues one run of an experiment. A run is derived from the contract: the controls are fixed
 * and each independent variable takes one of its declared values, so the form offers only
 * those. Submitting twice by accident queues one run, not two.
 */
export function RunForm({ projectId, experiment, blocked }: RunFormProps) {
  const id = useId()
  const navigate = useNavigate()
  const createRun = useCreateRun(projectId, experiment.id)
  const variables = Object.entries(experiment.protocol.independent_variables ?? {})
  const withSeed = needsSeed(experiment.protocol)
  const exactCommit = (experiment.protocol.execution.code?.mode ?? "ref") === "ref"
  const [chosen, setChosen] = useState<Record<string, number>>(() =>
    Object.fromEntries(variables.map(([name]) => [name, 0])),
  )
  const [seed, setSeed] = useState("")
  const [label, setLabel] = useState("")
  const [codeRef, setCodeRef] = useState("")
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<unknown>(null)
  const errors = fieldErrors(error)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const parameters = Object.fromEntries(
      variables.map(([name, values]) => [name, values[chosen[name] ?? 0]]),
    )
    createRun.mutate(
      {
        key,
        body: {
          parameters,
          seed: withSeed && seed !== "" ? Number(seed) : null,
          label: label.trim(),
          code_ref: codeRef.trim() || null,
        },
      },
      {
        onSuccess: (run) => {
          setKey(crypto.randomUUID()) // the next submission is a new run
          navigate(`/projects/${projectId}/runs/${run.id}`)
        },
        onError: setError,
      },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {variables.map(([name, values]) => (
          <FormField key={name} id={`${id}-${name}`} label={name} error={errors[name]}>
            <NativeSelect
              id={`${id}-${name}`}
              className="w-full"
              value={chosen[name] ?? 0}
              onChange={(event) => setChosen({ ...chosen, [name]: Number(event.target.value) })}
            >
              {values.map((value, index) => (
                <NativeSelectOption key={String(value)} value={index}>
                  {String(value)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FormField>
        ))}
        {withSeed && (
          <FormField id={`${id}-seed`} label="Seed" error={errors.seed}>
            <Input
              id={`${id}-seed`}
              type="number"
              min={0}
              step={1}
              required
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
            />
          </FormField>
        )}
        <FormField id={`${id}-label`} label="Label" hint="Optional, e.g. baseline.">
          <Input
            id={`${id}-label`}
            value={label}
            maxLength={200}
            onChange={(event) => setLabel(event.target.value)}
          />
        </FormField>
        {exactCommit && (
          <FormField
            id={`${id}-ref`}
            label="Commit to execute"
            hint={`Branch, tag or SHA. Default: ${experiment.protocol.execution.code?.ref ?? "HEAD"}, fixed to a commit now.`}
            error={errors.code_ref}
          >
            <Input
              id={`${id}-ref`}
              value={codeRef}
              className="font-mono"
              onChange={(event) => setCodeRef(event.target.value)}
            />
          </FormField>
        )}
      </div>
      {variables.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing varies in this experiment: every run uses the same parameters.
        </p>
      )}
      {error !== null && Object.keys(errors).length === 0 && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={blocked !== undefined || createRun.isPending}>
          Queue a run
        </Button>
        {blocked && <p className="text-sm text-muted-foreground">{blocked}</p>}
      </div>
    </form>
  )
}
