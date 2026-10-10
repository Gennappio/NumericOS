import { XIcon } from "lucide-react"
import { Button } from "@/components/ui/button"

/** A dismissible problem report. Used for failures of actions the person just took. */
export function Notice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
    >
      <p>{message}</p>
      <Button variant="ghost" size="icon" aria-label="Dismiss message" onClick={onDismiss}>
        <XIcon />
      </Button>
    </div>
  )
}
