import { useId, useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface GenerateFormProps {
  /** What the button does: "Write the theory", "Write it again". */
  action: string
  /** The instructions of the previous request, to start from. */
  instructions: string
  /** Why it cannot be asked now, if so. */
  blocked: string | null
  pending: boolean
  hint?: string
  onGenerate: (instructions: string) => void
}

/** The request to the agent for a document, with room for the researcher's own words. */
export function GenerateForm({
  action,
  instructions,
  blocked,
  pending,
  hint,
  onGenerate,
}: GenerateFormProps) {
  const id = useId()
  const [text, setText] = useState(instructions)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onGenerate(text.trim())
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor={`${id}-instructions`} className="text-sm font-medium">
        Instructions for the agent <span className="font-normal text-muted-foreground">(optional)</span>
      </label>
      <Textarea
        id={`${id}-instructions`}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={hint ?? "A language, an emphasis, what to leave out…"}
        rows={2}
        maxLength={5000}
        disabled={blocked !== null}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={blocked !== null || pending}>
          {action}
        </Button>
        {blocked && (
          <p role="status" className="text-sm text-amber-800">
            {blocked}
          </p>
        )}
      </div>
    </form>
  )
}
