import { useId, type ReactNode } from "react"

interface SectionProps {
  title: string
  /** One or two sentences under the title, when the section needs explaining. */
  description?: ReactNode
  /** Shown at the right of the title: an action or a short status. */
  aside?: ReactNode
  children: ReactNode
}

/** A titled part of a page. */
export function Section({ title, description, aside, children }: SectionProps) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 id={id} className="text-base font-medium">
            {title}
          </h2>
          {description && <p className="max-w-prose text-sm text-muted-foreground">{description}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  )
}
