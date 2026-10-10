import type { ReactNode } from "react"
import { Label } from "@/components/ui/label"

interface FormFieldProps {
  id: string
  label: string
  hint?: string
  error?: string
  children: ReactNode
}

/** Label, control, optional hint and the server's validation message for one form field. */
export function FormField({ id, label, hint, error, children }: FormFieldProps) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
