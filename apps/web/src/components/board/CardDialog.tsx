import { useId, useState, type FormEvent } from "react"
import type { Card, CardType, WorkflowStatus } from "@/api/client"
import { useCreateCard, useUpdateCard } from "@/api/queries"
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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { describeError, fieldErrors } from "@/lib/errors"
import { CARD_TYPE_LABELS, CARD_TYPES, STATUS_LABELS } from "@/lib/labels"
import { formatTimestamp } from "@/lib/time"

/** What the dialog is for: a new card in a column, or an existing card. */
export type CardDialogTarget =
  | { mode: "create"; status: WorkflowStatus }
  | { mode: "edit"; card: Card }

interface CardDialogProps {
  projectId: string
  statuses: WorkflowStatus[]
  open: boolean
  onOpenChange: (open: boolean) => void
  target: CardDialogTarget
}

export function CardDialog({ projectId, statuses, open, onOpenChange, target }: CardDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* The form mounts with the dialog, so every opening starts from the current card. */}
        <CardForm
          projectId={projectId}
          statuses={statuses}
          target={target}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

interface CardFormProps {
  projectId: string
  statuses: WorkflowStatus[]
  target: CardDialogTarget
  onDone: () => void
}

function CardForm({ projectId, statuses, target, onDone }: CardFormProps) {
  const id = useId()
  const card = target.mode === "edit" ? target.card : null
  const [title, setTitle] = useState(card?.title ?? "")
  const [type, setType] = useState<CardType>(card?.type ?? "task")
  const [status, setStatus] = useState<WorkflowStatus>(
    target.mode === "edit" ? target.card.workflow_status : target.status,
  )
  const [description, setDescription] = useState(card?.description ?? "")
  const [error, setError] = useState<unknown>(null)
  const createCard = useCreateCard(projectId)
  const updateCard = useUpdateCard(projectId)
  const pending = createCard.isPending || updateCard.isPending
  const errors = fieldErrors(error)
  const generalError = error !== null && Object.keys(errors).length === 0

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const fields = { type, title: title.trim(), description: description.trim() }
    const handlers = { onSuccess: onDone, onError: setError }
    if (card) {
      updateCard.mutate(
        { cardId: card.id, patch: { version: card.version, ...fields, workflow_status: status } },
        handlers,
      )
    } else {
      createCard.mutate({ ...fields, workflow_status: status }, handlers)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{card ? "Edit card" : "New card"}</DialogTitle>
        <DialogDescription>
          The type says what kind of research object this is. The workflow status says how far
          the work is, never whether a result holds.
        </DialogDescription>
      </DialogHeader>

      <FormField id={`${id}-title`} label="Title" error={errors.title}>
        <Input
          id={`${id}-title`}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          required
          maxLength={300}
          aria-invalid={errors.title ? true : undefined}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id={`${id}-type`} label="Type" error={errors.type}>
          <NativeSelect
            id={`${id}-type`}
            className="w-full"
            value={type}
            onChange={(event) => setType(event.target.value as CardType)}
          >
            {CARD_TYPES.map((option) => (
              <NativeSelectOption key={option} value={option}>
                {CARD_TYPE_LABELS[option]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FormField>
        <FormField id={`${id}-status`} label="Workflow status" error={errors.workflow_status}>
          <NativeSelect
            id={`${id}-status`}
            className="w-full"
            value={status}
            onChange={(event) => setStatus(event.target.value as WorkflowStatus)}
          >
            {statuses.map((option) => (
              <NativeSelectOption key={option} value={option}>
                {STATUS_LABELS[option]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FormField>
      </div>
      <FormField id={`${id}-description`} label="Description" error={errors.description}>
        <Textarea
          id={`${id}-description`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={20000}
        />
      </FormField>

      {card && (
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{card.id}</span> · version {card.version} · updated{" "}
          {formatTimestamp(card.updated_at)}
        </p>
      )}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}

      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
        <Button type="submit" disabled={pending}>
          {card ? "Save card" : "Create card"}
        </Button>
      </DialogFooter>
    </form>
  )
}
