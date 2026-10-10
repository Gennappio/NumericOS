import { Button } from "@/components/ui/button"
import { describeError } from "@/lib/errors"

interface ErrorPanelProps {
  title: string
  error: unknown
  onRetry: () => void
}

/** Shown instead of content that could not be loaded. Never replaced by placeholder data. */
export function ErrorPanel({ title, error, onRetry }: ErrorPanelProps) {
  return (
    <div role="alert" className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-medium">{title}</h2>
      <p className="text-sm text-muted-foreground">{describeError(error)}</p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}
