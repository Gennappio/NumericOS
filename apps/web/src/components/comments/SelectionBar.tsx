import { useId, useState, type FormEvent, type KeyboardEvent } from "react"
import type { AnnotationKind } from "@/api/client"
import type { Draft } from "@/components/comments/useCommenting"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { excerpt, KIND_ACTIONS, KIND_PROMPTS } from "@/lib/comments"

const KINDS: AnnotationKind[] = ["clarification", "change", "note"]
/** The three choices of the bar, each in the colour of its kind of comment. */
const KIND_BUTTONS: Record<AnnotationKind, string> = {
  clarification: "border-sky-300 bg-sky-50 text-sky-900 hover:bg-sky-100",
  change: "border-orange-300 bg-orange-50 text-orange-900 hover:bg-orange-100",
  note: "border-violet-300 bg-violet-50 text-violet-900 hover:bg-violet-100",
}

interface SelectionBarProps {
  draft: Draft
  /** The selected passage, as it is in the source. */
  quote: string
  saving: boolean
  onChange: (draft: Draft | null) => void
  onSave: (body: string) => void
}

/**
 * The small bar under a selected passage: ask for a clarification, request a change or add
 * a note, then the words of the comment. It is placed inside the box of the text, which must
 * be positioned.
 */
export function SelectionBar({ draft, quote, saving, onChange, onSave }: SelectionBarProps) {
  return (
    <div
      role="dialog"
      aria-label="Comment on the selected passage"
      className="absolute z-20 w-[min(22rem,100%)] rounded-lg border border-border bg-popover p-2 font-sans text-sm shadow-lg"
      style={{ top: draft.top, left: draft.left }}
      // The selection must survive a press on the bar: only a click acts.
      onMouseDown={(event) => {
        if (!(event.target instanceof HTMLTextAreaElement)) event.preventDefault()
      }}
      onMouseUp={(event) => event.stopPropagation()}
      onKeyUp={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
    >
      {draft.kind === null ? (
        <div className="flex flex-wrap gap-1">
          {KINDS.map((kind) => (
            <Button
              key={kind}
              size="sm"
              variant="outline"
              className={KIND_BUTTONS[kind]}
              onClick={() => onChange({ ...draft, kind })}
            >
              {KIND_ACTIONS[kind]}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
            Cancel
          </Button>
        </div>
      ) : (
        <DraftForm
          kind={draft.kind}
          quote={quote}
          saving={saving}
          onSave={onSave}
          onCancel={() => onChange(null)}
        />
      )}
    </div>
  )
}

interface DraftFormProps {
  kind: AnnotationKind
  quote: string
  saving: boolean
  onSave: (body: string) => void
  onCancel: () => void
}

function DraftForm({ kind, quote, saving, onSave, onCancel }: DraftFormProps) {
  const id = useId()
  const [body, setBody] = useState("")
  const needsText = kind !== "note"

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (needsText && !body.trim()) return
    onSave(body.trim())
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.currentTarget.form?.requestSubmit()
    }
    if (event.key === "Escape") onCancel()
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <p className="line-clamp-2 border-l-2 border-border pl-2 text-xs text-muted-foreground">
        {excerpt(quote, 160)}
      </p>
      <label htmlFor={`${id}-body`} className="text-xs font-medium">
        {KIND_PROMPTS[kind]}
      </label>
      <Textarea
        id={`${id}-body`}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        onKeyDown={keyDown}
        rows={3}
        maxLength={5000}
        autoFocus
      />
      <div className="flex justify-end gap-1">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={saving || (needsText && !body.trim())}>
          {KIND_ACTIONS[kind]}
        </Button>
      </div>
    </form>
  )
}
